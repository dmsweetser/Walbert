#!/usr/bin/env python3
"""
Standalone Audio Test Script for Walbert
Replicates audio_thread.py behaviors for troubleshooting Bluetooth, STT, and TTS.
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
from pynput import keyboard

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

def is_display_available():
    display = os.environ.get('DISPLAY')
    if display:
        return True
    try:
        return os.path.exists('/tmp/.X11-unix') or os.path.exists('/run/user/1000/wayland-0')
    except Exception:
        return False

def setup_bluetooth(bt_mac):
    if not bt_mac or bt_mac == "null":
        logger.info("No Bluetooth MAC configured; skipping BT setup.")
        return
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
    except Exception as e:
        logger.error(f"Bluetooth setup failed: {e}")

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

def tone(freq=1000, duration=0.2, bt_sink=None):
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
    def __init__(self, bt_sink=None):
        self.recording = False
        self.stop_event = threading.Event()
        self.bt_sink = bt_sink

    def on_press(self, key):
        try:
            if is_display_available():
                if key == keyboard.Key.media_play_pause:
                    logger.info("Play/Pause key pressed!")
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
        except Exception as e:
            logger.error(f"Error in keyboard listener: {e}")

    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.stop_event.clear()
        logger.info("Recording STARTED")
        tone(freq=1000, duration=0.2, bt_sink=self.bt_sink)

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self.stop_event.set()
        logger.info("Recording STOPPED")
        for _ in range(2):
            tone(freq=1000, duration=0.2, bt_sink=self.bt_sink)

    def start_listener(self):
        self._listener = keyboard.Listener(on_press=self.on_press)
        self._listener.start()


def capture_loop(bt_source):
    source = bt_source if bt_source and bt_source != "null" else None
    
    if source:
        logger.info(f"Starting STT capture from: {source}")
    else:
        logger.info("Starting STT capture from default microphone")

    try:
        cmd = ["pw-record", "--rate", "16000", "--channels", "1"]
        if source:
            cmd.extend(["--target", source])
        cmd.extend(["-"])
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logger.info("Attempting to start audio capture process...")
        time.sleep(20)
        
        # Read raw PCM data until interrupted
        raw_data = b""
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                raw_data += chunk
        except KeyboardInterrupt:
            logger.info("Capture interrupted by user.")
    except Exception as e:
        logger.error(f"Capture loop error: {e}")
    finally:
        if proc:
            proc.terminate()
            proc.wait()
    return raw_data

def process_recording_buffer(audio_data, stt_model):
    if not stt_model:
        logger.warning("STT model not loaded, cannot process recording")
        return None

    if len(audio_data) < 16000:
        logger.warning("Audio data too short to process.")
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
        tmp_f.write(audio_data)
        tmp_path = tmp_f.name

    try:
        result = stt_model.transcribe(tmp_path, fp16=False)
        text = result.get("text", "").strip()
        logger.info(f"STT Output: {text}")
        return text
    except Exception as e:
        logger.error(f"STT processing error: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def handle_console_response(text, tts_engine):
    if not tts_engine:
        logger.warning("TTS engine not loaded, cannot speak response")
        return
    try:
        tts_engine.say(text)
        tts_engine.runAndWait()
        logger.debug("TTS output played")
    except Exception as e:
        logger.error(f"TTS playback failed: {e}")

def main():
    config = load_config()
    bt_mac = config.get("bluetooth_device", "null")
    bt_sink = config.get("bluetooth_sink", "null")
    bt_source = config.get("bluetooth_source", "null")
    stt_enabled = config.get("stt_enabled", False)
    tts_enabled = config.get("tts_enabled", False)
    tts_voice = config.get("tts_voice", "default")

    print("=== Walbert Audio Test Standalone Script ===")
    print(f"BT MAC: {bt_mac}")
    print(f"BT Sink: {bt_sink}")
    print(f"BT Source: {bt_source}")
    print(f"STT Enabled: {stt_enabled}")
    print(f"TTS Enabled: {tts_enabled}")
    print(f"TTS Voice: {tts_voice}")
    print("============================================")

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

    print("\n[6] Starting Audio Capture (Ctrl+C to stop)...")
    raw_data = capture_loop(source)
    print(f"\nCaptured {len(raw_data)} bytes of raw PCM data.")

    if stt_model:
        print("\n[7] Processing Recording with STT...")
        stt_text = process_recording_buffer(raw_data, stt_model)
        if stt_text:
            print(f"Transcribed Text: {stt_text}")
            if tts_engine:
                print("\n[8] Testing TTS with Transcribed Text...")
                handle_console_response(stt_text, tts_engine)
        else:
            print("No text transcribed.")
    else:
        print("\nSTT model not loaded. Skipping transcription and TTS.")

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    main()