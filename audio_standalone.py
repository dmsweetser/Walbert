#!/usr/bin/env python3
"""
Walbert Standalone Audio Module (Offline, Whisper Edition)
Uses pydub for audio playback and pyttsx3 with espeak for TTS.
Uses OpenAI Whisper (base) for offline STT.
Automatically installs dependencies.
"""

import sys
import os
import subprocess
import threading
import time
import platform
from pathlib import Path
import numpy as np

# ============================================================
# Feature Flags
# ============================================================
ENABLE_STT_TTS_LOOPBACK = True   # Speak back recognized text for debugging


# ============================================================
# Dependency Installation
# ===============================================================
def install_system_dependencies():
    """Install system-level dependencies for audio processing."""
    if platform.system() == "Linux":
        print("[INFO] Installing system dependencies for Linux...", file=sys.stderr)
        subprocess.check_call(["sudo", "apt-get", "update"])
        subprocess.check_call(["sudo", "apt-get", "install", "-y",
                               "espeak", "ffmpeg", "portaudio19-dev"])
    elif platform.system() == "Darwin":  # macOS
        print("[INFO] Installing system dependencies for macOS...", file=sys.stderr)
        subprocess.check_call(["brew", "install", "espeak", "ffmpeg", "portaudio"])
    else:
        print("[ERROR] System dependency installation not supported for this OS. Please install manually.", file=sys.stderr)
        sys.exit(1)


def install_package(package):
    """Install a Python package if it's not already installed."""
    try:
        __import__(package)
    except ImportError:
        print(f"[INFO] Installing {package}...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def check_prerequisites():
    """Check and install all prerequisites."""
    install_system_dependencies()
    install_package("whisper")
    install_package("torch")
    install_package("pyttsx3")
    install_package("pyaudio")
    install_package("pydub")


# Check prerequisites before proceeding
check_prerequisites()

# ============================================================
# Imports AFTER installation
# ============================================================
import whisper
import pyaudio
import pyttsx3
from pydub import AudioSegment
from pydub.playback import play


# ============================================================
# Standalone Audio Class
# ============================================================
class StandaloneAudio:
    def __init__(self):
        # ----------------------------------------
        # Initialize TTS engine
        # ----------------------------------------
        try:
            self.engine = pyttsx3.init(driverName='espeak')
        except:
            print("[ERROR] Failed to initialize pyttsx3 with espeak. Falling back to default.", file=sys.stderr)
            self.engine = pyttsx3.init()

        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 1.0)
        self.engine.setProperty('voice', 'english-us')

        # ----------------------------------------
        # Initialize Whisper STT
        # ----------------------------------------
        print("[INFO] Loading Whisper model (base)...", file=sys.stderr)
        self.model = whisper.load_model("base")

        # ----------------------------------------
        # Audio input stream
        # ----------------------------------------
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=4096,
            stream_callback=self._audio_callback
        )

        # ----------------------------------------
        # State
        # ----------------------------------------
        self._running = False
        self._wake_word_detected = False
        self._silence_start = None
        self._command_buffer_pcm = []

        self.wake_word = "hey"
        self.silence_threshold = 2.5  # seconds

    # ============================================================
    # Audio Callback
    # ============================================================
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for processing audio data."""
        if not self._running:
            return (in_data, pyaudio.paContinue)

        # Convert raw PCM bytes → numpy array
        pcm = np.frombuffer(in_data, dtype=np.int16)

        # Append to buffer
        self._command_buffer_pcm.append(pcm)

        # Detect silence (very naive RMS check)
        rms = np.sqrt(np.mean(pcm.astype(np.float32) ** 2))
        silence = rms < 50  # threshold

        if not self._wake_word_detected:
            # Try quick wake-word detection using Whisper tiny model
            if silence:
                return (in_data, pyaudio.paContinue)

            # Run tiny model for wake word detection
            audio_data = np.concatenate(self._command_buffer_pcm).astype(np.float32) / 32768.0
            result = self.model.transcribe(audio_data, fp16=False)
            text = result["text"].lower().strip()

            if self.wake_word in text:
                self._wake_word_detected = True
                self._command_buffer_pcm = []  # reset buffer
                print(f"[STT] Wake word '{self.wake_word}' detected.", file=sys.stderr)

            return (in_data, pyaudio.paContinue)

        # Wake word already detected → capture command
        if silence:
            if self._silence_start is None:
                self._silence_start = time.time()
            elif (time.time() - self._silence_start) > self.silence_threshold:
                # Silence long enough → process command
                self._process_command()
                self._wake_word_detected = False
                self._command_buffer_pcm = []
                self._silence_start = None
        else:
            self._silence_start = None

        return (in_data, pyaudio.paContinue)

    # ============================================================
    # Process Command with Whisper
    # ============================================================
    def _process_command(self):
        if not self._command_buffer_pcm:
            return

        audio_data = np.concatenate(self._command_buffer_pcm).astype(np.float32) / 32768.0

        print("[STT] Processing command with Whisper...", file=sys.stderr)
        result = self.model.transcribe(audio_data, fp16=False)
        text = result["text"].strip()

        print(f"[STT] Command: {text}", file=sys.stderr)
        print(text, flush=True)

        if ENABLE_STT_TTS_LOOPBACK:
            self.engine.say(text)
            self.engine.runAndWait()

    # ============================================================
    # Public API
    # ============================================================
    def start_stt(self):
        """Start continuous speech recognition."""
        self._running = True
        self.stream.start_stream()
        print("[STT] Listening for wake word...", file=sys.stderr)

    def start_tts(self):
        """Read TTS commands from stdin and speak them."""
        def speak_loop():
            print("[TTS] Ready for text input via stdin...", file=sys.stderr)
            while self._running:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    text = line.strip()
                    if text:
                        self.engine.say(text)
                        self.engine.runAndWait()
                except Exception as e:
                    print(f"[TTS] Error: {e}", file=sys.stderr)

        thread = threading.Thread(target=speak_loop, daemon=True)
        thread.start()

    def stop(self):
        """Stop the audio module."""
        self._running = False
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()
        print("[STT/TTS] Stopped.", file=sys.stderr)


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    audio = StandaloneAudio()
    try:
        audio.start_stt()
        audio.start_tts()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        audio.stop()
        sys.exit(0)
