import numpy as np
import threading
import queue
import time
import logging
import subprocess
import os
import tempfile
import wave
import fcntl

logger = logging.getLogger("walbert.audio_thread")

class AudioIOThread(threading.Thread):
    """
    Drop-in replacement for AudioIOThread using Piper TTS + pw-play.
    - Listens continuously
    - One quiet beep when wake word is detected
    - Two quiet beeps when silence is detected and utterance is complete
    - Sends captured text to input_queue as ("user_input", text)
    - Uses Piper TTS + pw-play for speech output (PipeWire-compatible)
    """

    def __init__(self, input_queue: queue.Queue, config):
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.config = config

        self._running = False

        self._bt_mac = getattr(config, "bluetooth_device", None)
        self._bt_sink = getattr(config, "bluetooth_sink", None)
        self._bt_source = getattr(config, "bluetooth_source", None)
        self._piper_model = getattr(config, "piper_model", "en_US-libritts-r-medium.onnx")

        self._stt_model = None
        self._capture_proc = None

        # Rolling buffer for raw audio
        self._record_buffer = []
        self._record_lock = threading.Lock()

        # Wake-word + speech state
        self._state = "idle"
        self._user_buffer = ""
        self._silence_counter = 0

    # ----------------------------------------------------------------------
    # Thread lifecycle
    # ----------------------------------------------------------------------

    def run(self):
        logger.info("Audio IO Thread started")
        self._running = True

        self._setup_bluetooth()
        self._resolve_pipewire_bt_nodes()
        self._setup_stt()

        self._capture_loop()

        logger.info("Audio IO Thread exiting")

    def stop(self):
        logger.info("Audio IO Thread stopping")
        self._running = False
        if self._capture_proc:
            try:
                self._capture_proc.terminate()
            except Exception as e:
                logger.warning(f"Error terminating capture process: {e}")
            self._capture_proc = None

    # ----------------------------------------------------------------------
    # Setup
    # ----------------------------------------------------------------------

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
            logger.error(f"STT setup failed: {e}. Audio recording will not work without STT model.")
            self._stt_model = None

    # ----------------------------------------------------------------------
    # Beep helper
    # ----------------------------------------------------------------------

    def _quiet_beep(self, times=1, freq=100, duration=0.05):
        for _ in range(times):
            self._tone_quiet(freq=freq, duration=duration)
            time.sleep(0.05)

    def _tone_quiet(self, freq=100, duration=0.05):
        rate = 44100
        t = np.linspace(0, duration, int(rate * duration), False)
        tone = (0.1 * np.sin(freq * t * 2 * np.pi)).astype(np.float32)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wf = wave.open(f, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(4)
            wf.setframerate(rate)
            wf.writeframes(tone.tobytes())
            wf.close()
            wav_path = f.name

        if self._bt_sink and self._bt_sink != "null":
            subprocess.run(["pw-play", wav_path, "--target", self._bt_sink], check=False)
        else:
            subprocess.run(["pw-play", wav_path], check=False)

        os.unlink(wav_path)

    # ----------------------------------------------------------------------
    # Continuous capture + STT
    # ----------------------------------------------------------------------

    def _capture_loop(self):
        if not self._stt_model:
            logger.warning("No STT model loaded; capture loop will not process audio.")
        source = self._bt_source if self._bt_source and self._bt_source != "null" else None

        self._quiet_beep(1, 250)
        if source:
            logger.info(f"Starting continuous capture from: {source}")
        else:
            logger.info("Starting continuous capture from default microphone")

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

            while self._running:
                try:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        with self._record_lock:
                            self._record_buffer.append(chunk)
                except BlockingIOError:
                    pass

                if time.time() - last_transcribe > 2.0:
                    last_transcribe = time.time()
                    self._transcribe_chunk()

                time.sleep(0.01)

        except FileNotFoundError:
            logger.error("pw-record command not found. Check PipeWire configuration.")
        except Exception as e:
            logger.error(f"Error in capture loop: {e}")
        finally:
            if self._capture_proc:
                try:
                    self._capture_proc.terminate()
                except Exception:
                    pass
                self._capture_proc = None

    def _transcribe_chunk(self):
        if not self._stt_model:
            return

        with self._record_lock:
            if not self._record_buffer:
                return
            audio_data = b"".join(self._record_buffer)
            self._record_buffer.clear()

        if len(audio_data) < 16000:
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
            with wave.open(tmp_f, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
            tmp_path = tmp_f.name

        try:
            result = self._stt_model.transcribe(tmp_path, fp16=False)
            text = result.get("text", "").strip().lower()
            logger.info(f"STT: {text}")
            self._handle_transcript(text)
        except Exception as e:
            logger.error(f"STT error: {e}")
        finally:
            os.unlink(tmp_path)

    # ----------------------------------------------------------------------
    # Wake-word + silence handling
    # ----------------------------------------------------------------------

    def _handle_transcript(self, text: str):
        # Wake word detection
        if self._state == "idle":
            if "hey" in text:
                logger.info("Wake word detected — starting capture.")
                self._quiet_beep(times=1)
                self._state = "recording"
                self._user_buffer = ""
                self._silence_counter = 0
            return

        # Recording mode
        if self._state == "recording":
            if text:
                self._user_buffer += " " + text
                self._silence_counter = 0
            else:
                self._silence_counter += 1

            # End-of-speech detection: ~2 empty chunks
            if self._silence_counter >= 2:
                logger.info("Silence detected — finishing capture.")
                self._quiet_beep(2, 200)
                self._process_user_buffer()
                self._state = "idle"

    def _process_user_buffer(self):
        cleaned = self._user_buffer.strip()
        if not cleaned:
            logger.info("No content captured.")
            return

        logger.info(f"Captured user content: {cleaned}")
        self.input_queue.put(("user_input", cleaned))

    # ----------------------------------------------------------------------
    # TTS (Piper + pw-play)
    # ----------------------------------------------------------------------

    def handle_console_response(self, text: str):
        """
        Speak text using Piper TTS, streaming output directly to pw-play.
        No intermediate files needed.
        """
        if not self._running:
            return

        try:
            # Build Piper command
            # --output_raw: Output raw 16-bit PCM to stdout (22050 Hz, mono)
            piper_cmd = [
                "piper",
                "--model", self._piper_model,
                "--output_raw"
            ]

            # Build pw-play command
            play_cmd = [
                "pw-play",
                "--rate", "22050",
                "--channels", "1",
                "--format", "S16LE",
                "--process", "true",  # Keep process alive for streaming
                "-"
            ]

            if self._bt_sink and self._bt_sink != "null":
                play_cmd.extend(["--target", self._bt_sink])

            # Pipe Piper -> pw-play
            piper_proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            play_proc = subprocess.Popen(
                play_cmd,
                stdin=piper_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Close piper_proc's stdout in parent to allow play_proc to receive EOF
            piper_proc.stdout.close()

            # Write text to Piper
            piper_proc.communicate(input=text.encode())

            # Wait for both processes to finish
            play_proc.communicate()

            logger.debug("TTS output played via Piper + pw-play")

        except FileNotFoundError as e:
            logger.error(f"Piper or pw-play not found. Install with: pip install piper-tts (or use system package). Error: {e}")
        except Exception as e:
            logger.error(f"TTS playback failed: {e}")