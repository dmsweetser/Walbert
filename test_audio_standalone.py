#!/usr/bin/env python3
"""
Standalone Audio Test Script for Walbert (evdev version)
Drop-in replacement for audio_thread.py to validate Bluetooth, STT, TTS, and PipeWire.
Uses evdev instead of pynput so media keys still work in HFP mode.
"""

import os
import sys
import json
import subprocess
import time
import tempfile
import logging
import numpy as np
import wave
import threading
import queue
import fcntl
import select
from evdev import InputDevice, categorize, ecodes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("walbert.audio_test")


def load_config():
    config_path = "instance/config.json"
    if not os.path.exists(config_path):
        logger.error(f"Config file not found at {config_path}")
        sys.exit(1)
    with open(config_path, 'r') as f:
        return json.load(f)


def setup_bluetooth(bt_mac):
    if not bt_mac or bt_mac == "null":
        logger.info("No Bluetooth MAC configured; skipping BT setup.")
        return None
    try:
        logger.info(f"Configured Bluetooth MAC: {bt_mac}")
        subprocess.run(["bluetoothctl", "trust", bt_mac], check=False)
        for i in range(2):
            logger.info(f"Connecting to {bt_mac}, attempt {i+1}")
            subprocess.run(["bluetoothctl", "connect", bt_mac], check=False)
            time.sleep(1)

        info = subprocess.run(["bluetoothctl", "info", bt_mac],
                              capture_output=True, text=True)
        logger.info(f"bluetoothctl info:\n{info.stdout}")
        return bt_mac
    except Exception as e:
        logger.error(f"Bluetooth setup failed: {e}")
        return None


def resolve_pipewire_bt_nodes(bt_mac):
    if not bt_mac or bt_mac == "null":
        return None, None
    try:
        out = subprocess.run(["pw-cli", "ls", "Node"], capture_output=True, text=True)
        text = out.stdout
        mac = bt_mac.replace(":", "_")
        sink = None
        source = None

        for block in text.split("id"):
            if f"bluez_output.{mac}" in block and "node.name" in block:
                for line in block.splitlines():
                    if "node.name" in line:
                        sink = line.split('"')[1]
                        break
            if f"bluez_input.{mac}" in block and "node.name" in block:
                for line in block.splitlines():
                    if "node.name" in line:
                        source = line.split('"')[1]
                        break

        logger.info(f"Resolved PipeWire BT sink: {sink}, source: {source}")
        return sink, source
    except Exception as e:
        logger.error(f"Failed to resolve PipeWire BT nodes: {e}")
        return None, None


def setup_stt(stt_enabled):
    if not stt_enabled:
        logger.info("STT disabled.")
        return None
    try:
        import whisper
        logger.info("Loading Whisper base model...")
        model = whisper.load_model("base")
        logger.info("Whisper STT model loaded (base)")
        return model
    except Exception as e:
        logger.error(f"STT setup failed: {e}. Audio recording will not work without STT model.")
        return None


def setup_tts(tts_enabled, tts_voice):
    if not tts_enabled:
        logger.info("TTS disabled.")
        return None
    try:
        import pyttsx3
        engine = pyttsx3.init()
        if tts_voice != "default":
            engine.setProperty("voice", tts_voice)
        logger.info("TTS engine initialized")
        return engine
    except Exception as e:
        logger.error(f"TTS setup failed: {e}. Text-to-speech will not work.")
        return None


def tone(freq=150, duration=0.2, bt_sink=None):
    rate = 44100
    t = np.linspace(0, duration, int(rate * duration), False)
    tone_signal = np.sin(freq * t * 2 * np.pi).astype(np.float32)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wf = wave.open(f, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(4)
        wf.setframerate(rate)
        wf.writeframes(tone_signal.tobytes())
        wf.close()
        wav_path = f.name

    if bt_sink and bt_sink != "null":
        subprocess.run(["pw-play", wav_path, "--target", bt_sink], check=False)
    else:
        for player in ["aplay", "paplay", "pw-play"]:
            try:
                subprocess.run([player, wav_path], check=True)
                break
            except Exception:
                continue
        else:
            logger.warning("No working audio player found for beep")

    os.unlink(wav_path)


class AudioTestController:
    def __init__(self, bt_sink=None, bt_source=None, stt_model=None, tts_engine=None):
        self._recording = threading.Event()
        self._stop_event = threading.Event()
        self.bt_sink = bt_sink
        self.bt_source = bt_source
        self.stt_model = stt_model
        self.tts_engine = tts_engine
        self._capture_proc = None
        self._capture_thread = None
        self._record_buffer = []
        self._record_lock = threading.Lock()
        self._listener_thread = None
        self._input_device = None

    @property
    def recording(self):
        return self._recording.is_set()

    def _find_media_device(self):
        """Find the /dev/input/event* device that reports KEY_PLAYPAUSE."""
        for dev_path in os.listdir("/dev/input"):
            if not dev_path.startswith("event"):
                continue
            full = f"/dev/input/{dev_path}"
            try:
                dev = InputDevice(full)
                caps = dev.capabilities().get(ecodes.EV_KEY, [])
                if ecodes.KEY_PLAYPAUSE in caps:
                    logger.info(f"Found media key device: {full}")
                    return dev
            except Exception:
                continue
        logger.warning("No media key device found.")
        return None

    def _evdev_listener(self):
        logger.info("evdev listener started. Press Play/Pause to toggle recording.")
        for event in self._input_device.read_loop():
            if event.type == ecodes.EV_KEY and event.value == 1:
                print(event)
                if event.code == ecodes.KEY_PLAYPAUSE:
                    logger.info("Play/Pause key pressed!")
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()

    def start_listener(self):
        self._input_device = self._find_media_device()
        if not self._input_device:
            logger.error("No input device for media keys. Listener not started.")
            return
        self._listener_thread = threading.Thread(target=self._evdev_listener, daemon=True)
        self._listener_thread.start()

    def start_recording(self):
        logger.info("start_recording() called.")
        if self.recording:
            logger.info("Already recording.")
            return

        self._recording.set()
        self._stop_event.clear()
        logger.info("Recording STARTED")

        threading.Thread(target=lambda: tone(freq=1000, duration=0.2, bt_sink=self.bt_sink), daemon=True).start()

        if self._capture_thread and self._capture_thread.is_alive():
            return

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

    def stop_recording(self):
        logger.info("stop_recording() called.")
        if not self.recording:
            return

        self._recording.clear()
        self._stop_event.set()
        logger.info("Recording STOPPED")

        if self._capture_proc:
            try:
                self._capture_proc.terminate()
                self._capture_proc.wait(timeout=1)
            except Exception:
                pass
            finally:
                self._capture_proc = None

        threading.Thread(target=lambda: [tone(freq=1000, duration=0.2, bt_sink=self.bt_sink) for _ in range(2)], daemon=True).start()

    def _capture_loop(self):
        source = self.bt_source if self.bt_source and self.bt_source != "null" else None
        logger.info(f"Starting STT capture from: {source or 'default microphone'}")

        try:
            cmd = ["pw-record", "--rate", "16000", "--channels", "1"]
            if source:
                cmd.extend(["--target", source])
            cmd.extend(["-"])

            self._capture_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            fd = self._capture_proc.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            while self._recording.is_set() and not self._stop_event.is_set():
                try:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    with self._record_lock:
                        self._record_buffer.append(chunk)
                except BlockingIOError:
                    time.sleep(0.01)
                    continue

            if self._record_buffer and self.stt_model:
                self._process_recording_buffer()

        except Exception as e:
            logger.error(f"Error in capture loop: {e}")
        finally:
            if self._capture_proc:
                self._capture_proc.terminate()
                self._capture_proc.wait(timeout=1)
                self._capture_proc = None

    def _process_recording_buffer(self):
        with self._record_lock:
            audio_data = b"".join(self._record_buffer)
            self._record_buffer.clear()

        if len(audio_data) < 16000:
            logger.warning("Audio data too short.")
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
            tmp_f.write(audio_data)
            tmp_path = tmp_f.name

        try:
            result = self.stt_model.transcribe(tmp_path, fp16=False)
            text = result.get("text", "").strip()
            if text:
                logger.info(f"STT Output: {text}")
                if self.tts_engine:
                    self.tts_engine.say(text)
                    self.tts_engine.runAndWait()
        except Exception as e:
            logger.error(f"STT error: {e}")
        finally:
            os.unlink(tmp_path)

    def stop(self):
        self._recording.clear()
        self._stop_event.set()
        if self._capture_proc:
            self._capture_proc.terminate()
            self._capture_proc.wait(timeout=1)
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1)


def main():
    config = load_config()
    bt_mac = config.get("bluetooth_device", "null")
    bt_sink = config.get("bluetooth_sink", "null")
    bt_source = config.get("bluetooth_source", "null")
    stt_enabled = config.get("stt_enabled", False)
    tts_enabled = config.get("tts_enabled", False)
    tts_voice = config.get("tts_voice", "default")

    print("=== Walbert Audio Test Standalone Script (evdev) ===")
    print(f"BT MAC: {bt_mac}")
    print(f"BT Sink: {bt_sink}")
    print(f"BT Source: {bt_source}")
    print(f"STT Enabled: {stt_enabled}")
    print(f"TTS Enabled: {tts_enabled}")
    print(f"TTS Voice: {tts_voice}")
    print("===========================================")

    print("\n[1] Testing Bluetooth Setup...")
    setup_bluetooth(bt_mac)

    print("\n[2] Resolving PipeWire BT Nodes...")
    sink, source = resolve_pipewire_bt_nodes(bt_mac)

    print("\n[3] Testing Tone/Beep...")
    tone(bt_sink=sink)

    print("\n[4] Setting up STT...")
    stt_model = setup_stt(stt_enabled)

    print("\n[5] Setting up TTS...")
    tts_engine = setup_tts(tts_enabled, tts_voice)

    print("\n[6] Starting Audio Capture (Press Play/Pause)...")
    controller = AudioTestController(
        bt_sink=sink,
        bt_source=source,
        stt_model=stt_model,
        tts_engine=tts_engine
    )
    controller.start_listener()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        controller.stop()
        logger.info("Test complete. Exiting.")


if __name__ == "__main__":
    main()
