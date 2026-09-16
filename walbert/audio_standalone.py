#!/usr/bin/env python3
"""
Walbert Standalone Audio Module (Offline)
Automatically installs dependencies and uses pyttsx3 with espeak for TTS.
"""

import sys
import os
import subprocess
import threading
import queue
import time
import platform
from pathlib import Path

def install_package(package):
    """Install a Python package if it's not already installed."""
    try:
        __import__(package)
    except ImportError:
        print(f"[INFO] Installing {package}...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def install_espeak():
    """Install espeak if it's not already installed."""
    try:
        # Check if espeak is installed
        subprocess.run(["espeak", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("[INFO] espeak not found. Installing...", file=sys.stderr)
        if platform.system() == "Linux":
            subprocess.check_call(["sudo", "apt-get", "install", "-y", "espeak"])
        elif platform.system() == "Darwin":  # macOS
            subprocess.check_call(["brew", "install", "espeak"])
        else:
            print("[ERROR] espeak installation not supported for this OS. Please install manually.", file=sys.stderr)
            sys.exit(1)

def download_vosk_model(model_path="model"):
    """Download the VOSK model if it doesn't exist."""
    if not os.path.exists(model_path):
        print(f"[INFO] Downloading VOSK model to {model_path}...", file=sys.stderr)
        os.makedirs(model_path, exist_ok=True)
        # Download a small English model (replace with your preferred model)
        model_url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
        subprocess.check_call(["wget", "-q", "--show-progress", "-O", "-", model_url], cwd=model_path)
        subprocess.check_call(["unzip", "-o", "-q", "-"], cwd=model_path)
        # Remove the zip file after extraction
        os.remove(os.path.join(model_path, "vosk-model-small-en-us-0.15.zip"))

def check_prerequisites():
    """Check and install all prerequisites."""
    # Install Python packages
    install_package("vosk")
    install_package("pyttsx3")
    install_package("pyaudio")
    install_package("playsound")

    # Install espeak
    install_espeak()

    # Download VOSK model
    download_vosk_model()

# Check prerequisites before proceeding
check_prerequisites()

# Now import the required libraries
from vosk import Model, KaldiRecognizer
import pyaudio
import pyttsx3

class StandaloneAudio:
    def __init__(self):
        # Initialize TTS engine with espeak
        try:
            self.engine = pyttsx3.init(driverName='espeak')
        except:
            print("[ERROR] Failed to initialize pyttsx3 with espeak. Falling back to default.", file=sys.stderr)
            self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 1.0)
        self.engine.setProperty('voice', 'english-us')

        # Initialize VOSK for STT
        model_path = "model"
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"VOSK model not found at {model_path}. Download failed.")

        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.pa = pyaudio.PyAudio()

        # Audio stream for STT
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8000,
            stream_callback=self._audio_callback
        )

        # Flags and queues
        self._running = False
        self._wake_word_detected = False
        self._silence_start = None
        self._command_buffer = []

        # Wake word and silence threshold
        self.wake_word = "walbert"
        self.silence_threshold = 3  # seconds

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for processing audio data."""
        if not self._running:
            return (in_data, pyaudio.paContinue)

        if self.recognizer.AcceptWaveform(in_data):
            result = self.recognizer.Result()
            text = result.lower()

            # Check for wake word
            if not self._wake_word_detected and self.wake_word in text:
                self._wake_word_detected = True
                self._command_buffer = []
                print(f"[STT] Wake word '{self.wake_word}' detected.", file=sys.stderr)
                return (in_data, pyaudio.paContinue)

            # If wake word detected, capture the command
            if self._wake_word_detected:
                self._command_buffer.append(text)
                self._silence_start = None  # Reset silence timer

        else:
            # Check for silence
            if self._wake_word_detected and self._silence_start is None:
                self._silence_start = time.time()
            elif self._wake_word_detected and (time.time() - self._silence_start) > self.silence_threshold:
                # End of command due to silence
                command = " ".join(self._command_buffer)
                print(f"[STT] Command: {command}", file=sys.stderr)
                print(command, flush=True)  # Send to stdout
                self._wake_word_detected = False
                self._command_buffer = []

        return (in_data, pyaudio.paContinue)

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