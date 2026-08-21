"""
Audio Input/Output Thread for Walbert
Handles Whisper STT, TTS, Bluetooth audio routing, HID trigger detection,
and recording from Bluetooth microphone via PulseAudio/PipeWire (parec).
"""
import select
import threading
import queue
import time
import logging
import subprocess
import os
import tempfile
from typing import Callable

import evdev

logger = logging.getLogger('walbert.audio_thread')

class AudioIOThread(threading.Thread):
    def __init__(self, input_queue: queue.Queue, config, on_console_response: Callable[[str], None]):
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.config = config
        self.on_console_response = on_console_response
        self._running = False

        self._bt_mac = getattr(config, "bluetooth_device", None)
        self._bt_sink = getattr(config, "bluetooth_sink", None)
        self._bt_source = getattr(config, "bluetooth_source", None)

        self._stt_model = None
        self._tts_engine = None

        self._hid_device = None
        self._hid_thread = None

        self._recording = False
        self._audio_buffer = []
        self._record_lock = threading.Lock()

        self._capture_thread = None
        self._capture_process = None

    def run(self):
        logger.info("Audio IO Thread started")
        self._running = True
        self._setup_bluetooth()
        self._setup_stt()
        self._setup_tts()
        self._setup_hid()

        while self._running:
            with self._record_lock:
                if self._recording and self._audio_buffer:
                    self._process_audio_chunk()
            time.sleep(0.05)

    def stop(self):
        self._running = False
        self.stop_recording()
        if self._hid_thread and self._hid_thread.is_alive():
            self._hid_thread.join(timeout=1)
        logger.info("Audio IO Thread stopping")

    def _setup_bluetooth(self):
        """Ensure Bluetooth device is paired/connected; audio routing handled by PulseAudio/PipeWire."""
        if not self._bt_mac or self._bt_mac == "null":
            logger.info("No Bluetooth MAC configured; skipping BT setup.")
            return
        try:
            logger.info(f"Configured Bluetooth MAC: {self._bt_mac}")
            subprocess.run(["bluetoothctl", "trust", self._bt_mac], check=False,
                           capture_output=True, text=True)
            for i in range(2):
                logger.info(f"Connecting to {self._bt_mac}, attempt {i+1}")
                subprocess.run(["bluetoothctl", "connect", self._bt_mac], check=False,
                               capture_output=True, text=True)
                time.sleep(1.0)

            info = subprocess.run(["bluetoothctl", "info", self._bt_mac],
                                  capture_output=True, text=True)
            logger.info(f"bluetoothctl info:\n{info.stdout}")

            if self._bt_sink and self._bt_sink != "null":
                logger.info(f"Setting default sink to {self._bt_sink}")
                subprocess.run(["pactl", "set-default-sink", self._bt_sink],
                               check=False, capture_output=True, text=True)

            if self._bt_source and self._bt_source != "null":
                logger.info(f"Setting default source to {self._bt_source}")
                subprocess.run(["pactl", "set-default-source", self._bt_source],
                               check=False, capture_output=True, text=True)

        except Exception as e:
            logger.error(f"Bluetooth setup failed: {e}")

    def _setup_stt(self):
        """Initialize Whisper STT model."""
        if not getattr(self.config, "stt_enabled", False):
            logger.info("STT disabled in config.")
            self._stt_model = None
            return
        try:
            import whisper
            self._stt_model = whisper.load_model("base")
            logger.info("Whisper STT model loaded")
        except ImportError:
            logger.warning("whisper not installed. STT will be unavailable.")
            self._stt_model = None
        except Exception as e:
            logger.error(f"STT setup failed: {e}")
            self._stt_model = None

    def _setup_tts(self):
        """Initialize TTS engine."""
        if not getattr(self.config, "tts_enabled", False):
            logger.info("TTS disabled in config.")
            self._tts_engine = None
            return
        try:
            import pyttsx3
            self._tts_engine = pyttsx3.init()
            voice = getattr(self.config, "tts_voice", "default")
            if voice and voice != "default":
                self._tts_engine.setProperty('voice', voice)
            logger.info("TTS engine initialized")
        except ImportError:
            logger.warning("pyttsx3 not installed. TTS will be unavailable.")
            self._tts_engine = None
        except Exception as e:
            logger.error(f"TTS setup failed: {e}")
            self._tts_engine = None

    def _setup_hid(self):
        """Set up HID listener for Bluetooth play/pause button detection."""
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            if not devices:
                logger.info("No evdev input devices found for HID.")
                return

            for dev in devices:
                logger.info(f"HID candidate: name='{dev.name}', path='{dev.path}'")

            HID_KEYWORDS = [
                "hid", "consumer", "control", "avrcp", "media", "button", "sp-002", "headset"
            ]

            for dev in devices:
                name = dev.name.lower()
                if any(k in name for k in HID_KEYWORDS):
                    self._hid_device = dev
                    logger.info(f"HID listener attached to device: {dev.name} at {dev.path}")
                    break

            if self._hid_device:
                self._hid_thread = threading.Thread(target=self._hid_listener, daemon=True)
                self._hid_thread.start()
            else:
                logger.info("No suitable HID device found for media controls.")
        except Exception as e:
            logger.error(f"HID setup failed: {e}")

    def _hid_listener(self):
        """Listen for HID events, specifically the play/pause button."""
        try:
            if not self._hid_device:
                return

            logger.info(f"Starting HID event listener on {self._hid_device.path}")
            while self._running:
                try:
                    r, _, _ = select.select([self._hid_device], [], [], 0.1)
                    if r:
                        for event in self._hid_device.read():
                            if (event.type == evdev.ecodes.EV_KEY and
                                event.code == 164 and  # KEY_PLAYPAUSE
                                event.value == 1):
                                if self._recording:
                                    self.stop_recording()
                                else:
                                    self.start_recording()
                                status = "STARTED" if self._recording else "STOPPED"
                                logger.info(f"Recording {status} via Bluetooth play/pause button")
                                break
                except Exception as e:
                    if self._running:
                        logger.error(f"HID read error: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"HID listener failed: {e}")

    def _start_capture_thread(self):
        """Start a background thread that captures audio from the Bluetooth source via parec."""
        if self._capture_thread and self._capture_thread.is_alive():
            return
        if not self._bt_source or self._bt_source == "null":
            logger.warning("No Bluetooth source configured; cannot capture audio.")
            return

        def capture_loop():
            logger.info(f"Starting audio capture from source: {self._bt_source}")
            try:
                self._capture_process = subprocess.Popen(
                    ["parec", "--device", self._bt_source, "--rate", "16000",
                     "--format", "s16le", "--channels", "1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                while self._running and self._recording and self._capture_process:
                    chunk = self._capture_process.stdout.read(3200)  # 0.1s at 16kHz mono
                    if not chunk:
                        break
                    with self._record_lock:
                        self._audio_buffer.append(chunk)
            except Exception as e:
                logger.error(f"Audio capture failed: {e}")
            finally:
                if self._capture_process:
                    self._capture_process.terminate()
                    self._capture_process = None
                logger.info("Audio capture thread exiting.")

        self._capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self._capture_thread.start()

    def _stop_capture_thread(self):
        """Stop the background capture thread."""
        if self._capture_process:
            try:
                self._capture_process.terminate()
            except Exception:
                pass
            self._capture_process = None
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1)
        self._capture_thread = None

    def _process_audio_chunk(self):
        """Process recorded audio through STT and queue to agent."""
        if not self._stt_model:
            return
        try:
            audio_data = b''.join(self._audio_buffer)
            if len(audio_data) < 16000:  # ~1s minimum
                self._audio_buffer.clear()
                return

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                tmp_f.write(audio_data)
                tmp_path = tmp_f.name

            try:
                result = self._stt_model.transcribe(tmp_path, fp16=False)
                text = result.get('text', '').strip()
            finally:
                os.unlink(tmp_path)

            if text:
                logger.info(f"STT Output: {text}")
                self.input_queue.put(("user_input", text))
            self._audio_buffer.clear()
        except Exception as e:
            logger.error(f"STT processing failed: {e}")
            self._audio_buffer.clear()

    def handle_console_response(self, text: str):
        """Route console response to TTS (Bluetooth sink is default via pactl)."""
        if not self._tts_engine or not self._running:
            return
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            logger.debug("TTS output played")
        except Exception as e:
            logger.error(f"TTS playback failed: {e}")

    def start_recording(self):
        """Externally start recording."""
        with self._record_lock:
            self._recording = True
            self._audio_buffer.clear()
        logger.info("Recording started via API/HID")
        self._start_capture_thread()

    def stop_recording(self):
        """Externally stop recording."""
        with self._record_lock:
            self._recording = False
        logger.info("Recording stopped via API/HID")
        self._stop_capture_thread()
