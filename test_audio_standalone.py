#!/usr/bin/env python3
"""
Walbert Continuous Audio Listener
Listens constantly, transcribes constantly, and reacts to wake-words:
    "walbert start" → begin buffering
    "walbert stop"  → end buffering and process
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
import fcntl

# Logging
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
        logger.error(f"STT setup failed: {e}")
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
        logger.error(f"TTS setup failed: {e}")
        return None


class ContinuousAudioController:
    def __init__(self, bt_sink=None, bt_source=None, stt_model=None, tts_engine=None):
        self.bt_sink = bt_sink
        self.bt_source = bt_source
        self.stt_model = stt_model
        self.tts_engine = tts_engine

        self._capture_proc = None
        self._capture_thread = None
        self._record_buffer = []
        self._record_lock = threading.Lock()

        # Wake-word state
        self.state = "idle"
        self.user_buffer = ""

    def start(self):
        logger.info("Starting continuous audio capture...")
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

    def _capture_loop(self):
        source = self.bt_source if self.bt_source and self.bt_source != "null" else None
        logger.info(f"Capturing from: {source or 'default microphone'}")

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

            last_transcribe = time.time()

            while True:
                try:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        with self._record_lock:
                            self._record_buffer.append(chunk)
                except BlockingIOError:
                    pass

                # Transcribe every 2 seconds
                if time.time() - last_transcribe > 2.0:
                    last_transcribe = time.time()
                    self._transcribe_chunk()

                time.sleep(0.01)

        except Exception as e:
            logger.error(f"Error in capture loop: {e}")

    def _transcribe_chunk(self):
        with self._record_lock:
            if not self._record_buffer:
                return
            audio_data = b"".join(self._record_buffer)
            self._record_buffer.clear()

        if len(audio_data) < 16000:
            return

        # Write proper WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
            with wave.open(tmp_f, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
            tmp_path = tmp_f.name

        try:
            result = self.stt_model.transcribe(tmp_path, fp16=False)
            text = result.get("text", "").strip().lower()
            if text:
                logger.info(f"STT: {text}")
                self._handle_transcript(text)
        except Exception as e:
            logger.error(f"STT error: {e}")
        finally:
            os.unlink(tmp_path)

    def _handle_transcript(self, text):
        if "computer" in text:
            logger.info("Wake-word START detected.")
            self.state = "recording"
            self.user_buffer = ""
            return

        if "proceed" in text:
            logger.info("Wake-word STOP detected.")
            self.state = "idle"
            self._process_user_buffer()
            return

        if self.state == "recording":
            self.user_buffer += " " + text

    def _process_user_buffer(self):
        cleaned = self.user_buffer.strip()
        if not cleaned:
            logger.info("No content captured.")
            return

        logger.info(f"Captured user content: {cleaned}")

        if self.tts_engine:
            self.tts_engine.say(cleaned)
            self.tts_engine.runAndWait()


def main():
    config = load_config()
    bt_mac = config.get("bluetooth_device", "null")
    bt_sink = config.get("bluetooth_sink", "null")
    bt_source = config.get("bluetooth_source", "null")
    stt_enabled = config.get("stt_enabled", False)
    tts_enabled = config.get("tts_enabled", False)
    tts_voice = config.get("tts_voice", "default")

    print("=== Walbert Continuous Listener ===")
    print(f"BT MAC: {bt_mac}")
    print(f"BT Sink: {bt_sink}")
    print(f"BT Source: {bt_source}")
    print(f"STT Enabled: {stt_enabled}")
    print(f"TTS Enabled: {tts_enabled}")
    print(f"TTS Voice: {tts_voice}")
    print("===================================")

    setup_bluetooth(bt_mac)
    sink, source = resolve_pipewire_bt_nodes(bt_mac)
    stt_model = setup_stt(stt_enabled)
    tts_engine = setup_tts(tts_enabled, tts_voice)

    controller = ContinuousAudioController(
        bt_sink=sink,
        bt_source=source,
        stt_model=stt_model,
        tts_engine=tts_engine
    )
    controller.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        logger.info("Exiting.")


if __name__ == "__main__":
    main()
