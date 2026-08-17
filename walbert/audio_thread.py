"""
Audio Input/Output Thread for Walbert
Handles Whisper STT, TTS, Bluetooth audio routing, and HID trigger detection.
"""
import select
import threading
import queue
import time
import logging
import subprocess
import os
import json
from typing import Optional, Callable

import evdev

logger = logging.getLogger('walbert.audio_thread')

class AudioIOThread(threading.Thread):
    def __init__(self, input_queue: queue.Queue, config, on_console_response: Callable[[str], None]):
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.config = config
        self.on_console_response = on_console_response
        self._running = False
        self._bt_device = None
        self._stt_model = None
        self._tts_engine = None
        self._hid_device = None
        self._hid_thread = None
        self._recording = False
        self._audio_buffer = []
        self._record_lock = threading.Lock()

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
        if self._hid_thread and self._hid_thread.is_alive():
            self._hid_thread.join(timeout=1)
        logger.info("Audio IO Thread stopping")

    def _setup_bluetooth(self):
        """Use configured Bluetooth audio device and attempt pairing if needed."""
        if self.config.bluetooth_device and self.config.bluetooth_device != "null":
            self._bt_device = self.config.bluetooth_device
            self._pair_and_connect_bluetooth(self._bt_device)
            logger.info(f"Using configured Bluetooth audio device: {self._bt_device}")
        else:
            try:
                # Discover Bluetooth devices
                result = subprocess.run(['pactl', 'list', 'short', 'sources'], capture_output=True, text=True)
                sources = result.stdout.strip().split('\n')
                for line in sources:
                    if 'bluez' in line.lower() or 'bluetooth' in line.lower():
                        self._bt_device = line.split('\t')[1]
                        logger.info(f"Discovered Bluetooth audio device: {self._bt_device}")
                        break

                if not self._bt_device:
                    logger.warning("No Bluetooth audio device found. Falling back to default.")
                    self._bt_device = "alsa_output.pci-0000_00_1f.3.analog-stereo"

                # Attempt to pair and connect if not already connected
                if self._bt_device and "bluez" in self._bt_device.lower():
                    self._pair_and_connect_bluetooth(self._bt_device)

            except Exception as e:
                logger.error(f"Bluetooth setup failed: {e}")
                self._bt_device = None

    def _pair_and_connect_bluetooth(self, device_mac: str):
        """Pair and connect to a Bluetooth device using bluetoothctl."""
        try:
            # Check if the device is already paired
            check_paired = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True, text=True
            )
            if device_mac not in check_paired.stdout:
                # Pair the device
                subprocess.run(
                    ['bluetoothctl', 'pair', device_mac],
                    check=True,
                    capture_output=True, text=True
                )
                logger.info(f"Paired with Bluetooth device: {device_mac}")

            # Connect to the device
            subprocess.run(
                ['bluetoothctl', 'connect', device_mac],
                check=True,
                capture_output=True, text=True
            )
            logger.info(f"Connected to Bluetooth device: {device_mac}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Bluetooth pairing/connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Bluetooth pairing/connection: {e}")

    def _setup_stt(self):
        """Initialize Whisper STT model."""
        if not self.config.stt_enabled:
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
        if not self.config.tts_enabled:
            logger.info("TTS disabled in config.")
            self._tts_engine = None
            return
        try:
            import pyttsx3
            self._tts_engine = pyttsx3.init()
            if self.config.tts_voice and self.config.tts_voice != "default":
                self._tts_engine.setProperty('voice', self.config.tts_voice)
            logger.info("TTS engine initialized")
        except ImportError:
            logger.warning("pyttsx3 not installed. TTS will be unavailable.")
            self._tts_engine = None
        except Exception as e:
            logger.error(f"TTS setup failed: {e}")
            self._tts_engine = None

    def _setup_hid(self):
        """Set up HID listener for trigger detection."""
        try:
            import evdev
            from select import select

            # Find HID devices
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            for dev in devices:
                if 'keyboard' in dev.name.lower() or 'button' in dev.name.lower() or 'keypad' in dev.name.lower():
                    self._hid_device = dev
                    logger.info(f"HID listener attached to {dev.name} at {dev.path}")
                    break

            if self._hid_device:
                self._hid_thread = threading.Thread(target=self._hid_listener, daemon=True)
                self._hid_thread.start()
        except Exception as e:
            logger.error(f"HID setup failed: {e}")

    def _hid_listener(self):
        """Listen for HID events to toggle recording."""
        try:
            if not self._hid_device:
                return

            logger.info(f"Starting HID event listener on {self._hid_device.path}")
            while self._running:
                try:
                    # Use select with timeout to allow periodic checks of self._running
                    r, _, _ = select([self._hid_device], [], [], 0.1)
                    if r:
                        for event in self._hid_device.read():
                            if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                                # Key pressed - toggle recording
                                with self._record_lock:
                                    self._recording = not self._recording
                                status = "STARTED" if self._recording else "STOPPED"
                                logger.info(f"Recording {status} via HID trigger (Key code: {event.code})")
                                break
                except Exception as e:
                    if self._running:
                        logger.error(f"HID read error: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"HID listener failed: {e}")

    def _process_audio_chunk(self):
        """Process recorded audio through STT and queue to agent."""
        if not self._stt_model:
            return
        try:
            audio_data = b''.join(self._audio_buffer)
            if len(audio_data) < 1000:  # Minimum threshold
                self._audio_buffer.clear()
                return

            import tempfile
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
        """Route console response to TTS and Bluetooth speaker."""
        if not self._tts_engine or not self._running:
            return
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            logger.debug("TTS output sent to Bluetooth speaker")
        except Exception as e:
            logger.error(f"TTS playback failed: {e}")

    def start_recording(self):
        """Externally start recording."""
        with self._record_lock:
            self._recording = True
        logger.info("Recording started via API")

    def stop_recording(self):
        """Externally stop recording."""
        with self._record_lock:
            self._recording = False
        logger.info("Recording stopped via API")