"""
Audio Input/Output Thread for Walbert (Wake Word Trigger Edition)
- Whisper STT
- TTS via pyttsx3
- Bluetooth audio via PipeWire
- Recording via pw-record
- Trigger via wake word ("walbert") on BT mic
"""

import threading
import queue
import time
import logging
import subprocess
import os
import tempfile

logger = logging.getLogger("walbert.audio_thread")

WAKE_WORD = "walbert"


class AudioIOThread(threading.Thread):
    def __init__(self, input_queue: queue.Queue, config, on_console_response):
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.config = config
        self.on_console_response = on_console_response

        self._running = False
        self._recording = False
        self._audio_buffer = []
        self._record_lock = threading.Lock()

        self._bt_mac = getattr(config, "bluetooth_device", None)
        self._bt_sink = getattr(config, "bluetooth_sink", None)
        self._bt_source = getattr(config, "bluetooth_source", None)

        self._stt_model = None
        self._wake_model = None
        self._tts_engine = None

        self._capture_thread = None
        self._capture_process = None
        self._wake_thread = None
        self._wake_proc = None

    def run(self):
        logger.info("Audio IO Thread started")
        self._running = True

        self._setup_bluetooth()
        self._resolve_pipewire_bt_nodes()
        self._setup_stt()
        self._setup_wake_word()
        self._setup_tts()
        self._start_wake_word_listener()

        while self._running:
            with self._record_lock:
                if self._recording and self._audio_buffer:
                    self._process_audio_chunk()
            time.sleep(0.05)

    def stop(self):
        self._running = False
        self.stop_recording()
        self._stop_wake_word_listener()
        logger.info("Audio IO Thread stopping")

    def _setup_bluetooth(self):
        if not self._bt_mac or self._bt_mac == "null":
            logger.info("No Bluetooth MAC configured; skipping BT setup.")
            return
        try:
            logger.info(f"Configured Bluetooth MAC: {self._bt_mac}")
            subprocess.run(["bluetoothctl", "trust", self._bt_mac], check=False)
            for i in range(2):
                logger.info(f"Connecting to {self._bt_mac}, attempt {i+1}")
                subprocess.run(["bluetoothctl", "connect", self._bt_mac], check=False)
                time.sleep(1)

            info = subprocess.run(["bluetoothctl", "info", self._bt_mac],
                                  capture_output=True, text=True)
            logger.info(f"bluetoothctl info:\n{info.stdout}")
        except Exception as e:
            logger.error(f"Bluetooth setup failed: {e}")

    def _resolve_pipewire_bt_nodes(self):
        if not self._bt_mac or self._bt_mac == "null":
            return
        try:
            out = subprocess.run(["pw-cli", "ls", "Node"], capture_output=True, text=True)
            text = out.stdout
            mac = self._bt_mac.replace(":", "_")
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

            if sink:
                self._bt_sink = sink
            if source:
                self._bt_source = source

            logger.info(f"Resolved PipeWire BT sink: {self._bt_sink}, source: {self._bt_source}")
        except Exception as e:
            logger.error(f"Failed to resolve PipeWire BT nodes: {e}")

    def _setup_stt(self):
        if not getattr(self.config, "stt_enabled", False):
            logger.info("STT disabled.")
            return
        try:
            import whisper
            self._stt_model = whisper.load_model("base")
            logger.info("Whisper STT model loaded (base)")
        except Exception as e:
            logger.error(f"STT setup failed: {e}")
            self._stt_model = None

    def _setup_wake_word(self):
        if not getattr(self.config, "stt_enabled", False):
            logger.info("Wake word disabled because STT is disabled.")
            return
        try:
            import whisper
            self._wake_model = whisper.load_model("tiny")
            logger.info("Wake word Whisper model loaded (tiny)")
        except Exception as e:
            logger.error(f"Wake word setup failed: {e}")
            self._wake_model = None

    def _setup_tts(self):
        if not getattr(self.config, "tts_enabled", False):
            logger.info("TTS disabled.")
            return
        try:
            import pyttsx3
            self._tts_engine = pyttsx3.init()
            voice = getattr(self.config, "tts_voice", "default")
            if voice != "default":
                self._tts_engine.setProperty("voice", voice)
            logger.info("TTS engine initialized")
        except Exception as e:
            logger.error(f"TTS setup failed: {e}")
            self._tts_engine = None

    def _start_wake_word_listener(self):
        if not self._bt_source or self._bt_source == "null":
            logger.info("No BT source; wake word listener not started.")
            return
        if not self._wake_model:
            logger.info("No wake word model; wake word listener not started.")
            return

        def wake_loop():
            logger.info(f"Starting wake word listener on PipeWire source: {self._bt_source}")
            try:
                self._wake_proc = subprocess.Popen(
                    ["pw-record", "--target", self._bt_source,
                     "--rate", "16000", "--channels", "1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                buffer = b""
                while self._running:
                    chunk = self._wake_proc.stdout.read(3200)
                    if not chunk:
                        continue
                    buffer += chunk

                    # Use ~2 seconds of audio for wake word detection
                    if len(buffer) >= 32000:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                            tmp_f.write(buffer)
                            tmp_path = tmp_f.name
                        try:
                            result = self._wake_model.transcribe(tmp_path, fp16=False)
                            text = result.get("text", "").strip()
                            if text:
                                logger.debug(f"Wake word chunk text: {text}")
                                if WAKE_WORD in text.lower():
                                    logger.info("Wake word detected, starting recording.")
                                    self.start_recording()
                        except Exception as e:
                            logger.error(f"Wake word transcription failed: {e}")
                        finally:
                            os.unlink(tmp_path)
                        buffer = b""
            except Exception as e:
                logger.error(f"Wake word listener failed: {e}")
            finally:
                if self._wake_proc:
                    try:
                        self._wake_proc.terminate()
                    except Exception:
                        pass
                    self._wake_proc = None
                logger.info("Wake word listener exiting.")

        self._wake_thread = threading.Thread(target=wake_loop, daemon=True)
        self._wake_thread.start()

    def _stop_wake_word_listener(self):
        if self._wake_proc:
            try:
                self._wake_proc.terminate()
            except Exception:
                pass
            self._wake_proc = None
        if self._wake_thread and self._wake_thread.is_alive():
            self._wake_thread.join(timeout=1)
        self._wake_thread = None

    def _start_capture_thread(self):
        if self._capture_thread and self._capture_thread.is_alive():
            return
        if not self._bt_source or self._bt_source == "null":
            logger.warning("No Bluetooth source configured; cannot capture audio.")
            return

        def capture_loop():
            logger.info(f"Starting audio capture from PipeWire source: {self._bt_source}")
            try:
                self._capture_process = subprocess.Popen(
                    ["pw-record", "--target", self._bt_source,
                     "--rate", "16000", "--channels", "1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                while self._running and self._recording:
                    chunk = self._capture_process.stdout.read(3200)
                    if not chunk:
                        break
                    with self._record_lock:
                        self._audio_buffer.append(chunk)
            except Exception as e:
                logger.error(f"Audio capture failed: {e}")
            finally:
                if self._capture_process:
                    try:
                        self._capture_process.terminate()
                    except Exception:
                        pass
                    self._capture_process = None
                logger.info("Audio capture thread exiting.")
        self._capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self._capture_thread.start()

    def _stop_capture_thread(self):
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
        if not self._stt_model:
            return
        try:
            audio_data = b"".join(self._audio_buffer)
            if len(audio_data) < 16000:
                self._audio_buffer.clear()
                return
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                tmp_f.write(audio_data)
                tmp_path = tmp_f.name
            try:
                result = self._stt_model.transcribe(tmp_path, fp16=False)
                text = result.get("text", "").strip()
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
        if not self._tts_engine or not self._running:
            return
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            logger.debug("TTS output played")
        except Exception as e:
            logger.error(f"TTS playback failed: {e}")

    def start_recording(self):
        with self._record_lock:
            self._recording = True
            self._audio_buffer.clear()
        logger.info("Recording STARTED")
        self._start_capture_thread()

    def stop_recording(self):
        with self._record_lock:
            self._recording = False
        logger.info("Recording STOPPED")
        self._stop_capture_thread()
