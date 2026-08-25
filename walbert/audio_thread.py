import numpy as np
import pyaudio
from pynput import keyboard
import threading
import queue
import time
import logging
import subprocess
import os
import tempfile

logger = logging.getLogger("walbert.audio_thread")

class AudioIOThread(threading.Thread):
    """
    Drop-in replacement for AudioIOThread using play/pause key to toggle recording.
    - Beeps once when recording starts
    - Beeps twice when recording stops
    """

    def __init__(self, input_queue: queue.Queue, config, on_console_response):
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.config = config
        self.on_console_response = on_console_response

        self._running = False
        self._recording = False

        self._bt_mac = getattr(config, "bluetooth_device", None)
        self._bt_sink = getattr(config, "bluetooth_sink", None)
        self._bt_source = getattr(config, "bluetooth_source", None)

        self._stt_model = None
        self._tts_engine = None

        self._capture_proc = None
        self._capture_thread = None

        # Rolling buffers
        self._record_buffer = []
        self._record_lock = threading.Lock()

    # ----------------------------------------------------------------------
    # Thread lifecycle
    # ----------------------------------------------------------------------

    def run(self):
        logger.info("Audio IO Thread started")
        self._running = True

        self._setup_bluetooth()
        self._resolve_pipewire_bt_nodes()
        self._setup_stt()
        self._setup_tts()

        while self._running:
            # Process STT recording buffer
            with self._record_lock:
                if self._recording and self._record_buffer:
                    self._process_recording_buffer()
            time.sleep(0.05)

    def stop(self):
        self._running = False
        self.stop_recording()
        logger.info("Audio IO Thread stopping")

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
            logger.error(f"TTS setup failed: {e}. Text-to-speech will not work.")
            self._tts_engine = None

    # ----------------------------------------------------------------------
    # Beep helper
    # ----------------------------------------------------------------------

    def _beep(self, times=1):
        for _ in range(times):
            self.tone()

    def tone(self, freq=1000, duration=0.2):
        import numpy as np
        import tempfile
        import subprocess
        import os

        rate = 44100
        t = np.linspace(0, duration, int(rate * duration), False)
        tone = np.sin(freq * t * 2 * np.pi).astype(np.float32)

        # Write WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import wave
            wf = wave.open(f, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(4)
            wf.setframerate(rate)
            wf.writeframes(tone.tobytes())
            wf.close()
            wav_path = f.name

        # Play through Bluetooth sink or fallback
        if self._bt_sink and self._bt_sink != "null":
            subprocess.run(["pw-play", wav_path, "--target", self._bt_sink], check=False)
        else:
            # Fallback to default audio output
            for player in ["aplay", "paplay", "pw-play"]:
                try:
                    subprocess.run([player, wav_path], check=True)
                    break
                except Exception:
                    continue
            else:
                logger.warning("No working audio player found for beep")

        os.unlink(wav_path)

    def on_press(self, key):
            try:
                if key == keyboard.Key.media_play_pause:
                    logger.info("Play/Pause key pressed!")
                    if self._recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
            except Exception as e:
                logger.error(f"Error in keyboard listener: {e}")

    # ----------------------------------------------------------------------
    # Recording (STT)
    # ----------------------------------------------------------------------

    def start_recording(self):
        with self._record_lock:
            self._recording = True
            self._record_buffer.clear()
        logger.info("Recording STARTED")
        self._beep(1)  # Single beep

        if self._capture_thread and self._capture_thread.is_alive():
            return

        def capture_loop():
            source = self._bt_source if self._bt_source and self._bt_source != "null" else None
            
            if source:
                logger.info(f"Starting STT capture from: {source}")
            else:
                logger.info("Starting STT capture from default microphone")

            try:
                cmd = ["pw-record", "--rate", "16000", "--channels", "1"]
                if source:
                    cmd.extend(["--target", source])
                
                self._capture_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Wait for the process to start successfully
                self._capture_proc.wait(timeout=5)
                logger.info("Audio capture process started successfully.")

            except FileNotFoundError:
                logger.error("pw-record command not found. Check pipewire configuration.")
                with self._record_lock:
                    self._recording = False
            except subprocess.TimeoutExpired:
                logger.error("Failed to start audio capture process within timeout.")
                with self._record_lock:
                    self._recording = False
            except Exception as e:
                logger.error(f"Audio capture failed unexpectedly: {e}")
                with self._record_lock:
                    self._recording = False
            finally:
                if self._capture_proc:
                    self._capture_proc.terminate()
                    self._capture_proc.wait(timeout=1)
                    self._capture_proc = None
                logger.info("Audio capture thread exiting.")

        self._capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self._capture_thread.start()

    def stop_recording(self):
        with self._record_lock:
            self._recording = False
        logger.info("Recording STOPPED")
        self._beep(5)

        if self._capture_proc:
            try:
                self._capture_proc.terminate()
            except Exception as e:
                logger.warning(f"Error terminating capture process: {e}")
            self._capture_proc = None

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1)
        self._capture_thread = None

    # ----------------------------------------------------------------------
    # STT processing
    # ----------------------------------------------------------------------

    def _process_recording_buffer(self):
        if not self._stt_model:
            logger.warning("STT model not loaded, cannot process recording")
            self._record_buffer.clear()
            return

        audio_data = b"".join(self._record_buffer)
        if len(audio_data) < 16000:
            self._record_buffer.clear()
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

        self._record_buffer.clear()

    # ----------------------------------------------------------------------
    # TTS
    # ----------------------------------------------------------------------

    def handle_console_response(self, text: str):
        if not self._tts_engine or not self._running:
            if not self._tts_engine:
                logger.warning("TTS engine not loaded, cannot speak response")
            return
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            logger.debug("TTS output played")
        except Exception as e:
            logger.error(f"TTS playback failed: {e}")