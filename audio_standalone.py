#!/usr/bin/env python3
"""
Walbert Standalone Audio Module (Offline, Faster-Whisper + WebRTC VAD Edition)

- STT: faster-whisper (base) running locally
- VAD: WebRTC VAD for speech detection
- Wake word: "computer" detected from transcribed text
- TTS: pyttsx3 with espeak
- Debug: console output of audio → text, optional STT→TTS loopback
- Audio Feedback: Single beep on start, double-beep on successful input capture

This script is fully self-contained and will attempt to install all dependencies.
"""

import sys
import os
import subprocess
import threading
import time
import platform
from pathlib import Path
from collections import deque

import numpy as np

# ============================================================
# Feature Flags
# ============================================================
ENABLE_STT_TTS_LOOPBACK = False  # Speak back recognized text for debugging

# ============================================================
# Dependency Installation
# ============================================================

def run_command(command, error_message, suppress_output=False):
    """Run a shell command and handle errors gracefully."""
    try:
        stdout = subprocess.DEVNULL if suppress_output else None
        stderr = subprocess.DEVNULL if suppress_output else None
        subprocess.check_call(command, stdout=stdout, stderr=stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] {error_message}", file=sys.stderr)
        print(f"[DEBUG] Command failed: {' '.join(command)}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        return False

def install_system_dependencies():
    """Install system-level dependencies for audio processing."""
    if platform.system() == "Linux":
        print("[INFO] Installing system dependencies for Linux...", file=sys.stderr)

        # Update package lists
        run_command(
            ["sudo", "apt-get", "update"],
            "Failed to update package lists. Some system dependencies may not be installed.",
            suppress_output=True
        )

        # Install required packages
        system_packages = [
            "espeak",
            "ffmpeg",
            "portaudio19-dev",
            "pulseaudio",
        ]

        for package in system_packages:
            run_command(
                ["sudo", "apt-get", "install", "-y", package],
                f"Failed to install {package}. You may need to install it manually.",
                suppress_output=True
            )

    elif platform.system() == "Darwin":  # macOS
        print("[INFO] Installing system dependencies for macOS...", file=sys.stderr)

        # Check if Homebrew is installed
        if not run_command(["brew", "--version"], "Homebrew not found. Please install Homebrew first."):
            print("[ERROR] Homebrew is required for macOS. Install it from https://brew.sh", file=sys.stderr)
            return False

        # Install required packages
        system_packages = ["espeak", "ffmpeg", "portaudio"]

        for package in system_packages:
            run_command(
                ["brew", "install", package],
                f"Failed to install {package}. You may need to install it manually.",
                suppress_output=True
            )
    else:
        print(
            "[ERROR] System dependency installation not supported for this OS. "
            "Please install the following manually: espeak, ffmpeg, portaudio.",
            file=sys.stderr,
        )
        return False
    return True

def install_python_package(package):
    """Install a Python package if it's not already installed."""
    try:
        __import__(package)
        print(f"[INFO] {package} is already installed.", file=sys.stderr)
        return True
    except ImportError:
        print(f"[INFO] Installing {package}...", file=sys.stderr)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except subprocess.CalledProcessError:
            print(f"[ERROR] Failed to install {package}. You may need to install it manually.", file=sys.stderr)
            return False

def check_prerequisites():
    """Check and install all prerequisites."""
    print("[INFO] Checking and installing prerequisites...", file=sys.stderr)

    # Install system dependencies
    install_system_dependencies()

    # Install Python packages
    python_packages = [
        "systemtools",
        "wheel",
        "faster-whisper",
        "torch",
        "webrtcvad-wheels",
        "pyttsx3",
        "pyaudio",
        "pydub",
    ]

    for package in python_packages:
        install_python_package(package)

# Check prerequisites before proceeding
check_prerequisites()

# ============================================================
# Imports AFTER installation
# ============================================================
from faster_whisper import WhisperModel
import webrtcvad
import pyaudio
import pyttsx3
from pydub import AudioSegment
from pydub.playback import play
from pydub.generators import Sine

# ============================================================
# Helper Functions
# ============================================================

def pcm_to_float32(pcm: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 normalized to [-1, 1]."""
    return pcm.astype(np.float32) / 32768.0

def frame_generator(pcm: np.ndarray, sample_rate: int, frame_duration_ms: int = 30):
    """
    Generate frames of fixed duration from PCM data.
    Returns raw bytes suitable for WebRTC VAD.
    """
    n_samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
    total_samples = len(pcm)
    offset = 0
    while offset + n_samples_per_frame <= total_samples:
        frame = pcm[offset : offset + n_samples_per_frame]
        yield frame.tobytes()
        offset += n_samples_per_frame

def is_speech_webrtc(pcm: np.ndarray, vad: webrtcvad.Vad, sample_rate: int) -> bool:
    """
    Use WebRTC VAD to determine if the PCM chunk contains speech.
    """
    if len(pcm) == 0:
        return False

    speech_frames = 0
    total_frames = 0

    for frame in frame_generator(pcm, sample_rate, frame_duration_ms=30):
        total_frames += 1
        if vad.is_speech(frame, sample_rate):
            speech_frames += 1

    if total_frames == 0:
        return False

    # Consider it speech if a reasonable fraction of frames are speech
    return speech_frames / total_frames > 0.3

def generate_beep(duration_ms: int = 100, frequency: int = 800):
    """Generate a beep sound using Pydub."""
    beep = Sine(frequency).to_audio_segment(duration=duration_ms)
    return beep

def play_beep(beep):
    """Play a beep sound."""
    play(beep)

# ============================================================
# Standalone Audio Class
# ============================================================

class StandaloneAudio:
    def __init__(self):
        # ----------------------------------------
        # Initialize TTS engine
        # ----------------------------------------
        try:
            self.engine = pyttsx3.init(driverName="espeak")
        except Exception:
            print(
                "[ERROR] Failed to initialize pyttsx3 with espeak. Falling back to default.",
                file=sys.stderr,
            )
            self.engine = pyttsx3.init()

        self.engine.setProperty("rate", 150)
        self.engine.setProperty("volume", 1.0)
        self.engine.setProperty("voice", "english-us")

        # ----------------------------------------
        # Initialize faster-whisper STT
        # ----------------------------------------
        print("[INFO] Loading faster-whisper model (base)...", file=sys.stderr)
        self.model = WhisperModel("base", device="cpu", compute_type="int8")

        # ----------------------------------------
        # Initialize VAD (WebRTC)
        # ----------------------------------------
        self.sample_rate = 16000
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(2)  # Aggressiveness: 0–3 (3 is most aggressive)

        # ----------------------------------------
        # Audio input stream
        # ----------------------------------------
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=4096,
            stream_callback=self._audio_callback,
        )

        # ----------------------------------------
        # State
        # ----------------------------------------
        self._running = False
        self._in_utterance = False
        self._utterance_buffer = deque()
        self._last_speech_time = None

        self.wake_word = "computer"

        # Silence threshold after speech ends to finalize utterance
        self.silence_threshold = 1.5  # seconds

        # Beep sounds
        self.single_beep = generate_beep(duration_ms=100)
        self.double_beep = generate_beep(duration_ms=200)

    # ============================================================
    # Audio Callback
    # ============================================================
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for processing audio data."""
        if not self._running:
            return (in_data, pyaudio.paContinue)

        # Convert raw PCM bytes → numpy array
        pcm = np.frombuffer(in_data, dtype=np.int16)

        # VAD: determine if this chunk contains speech
        has_speech = is_speech_webrtc(pcm, self.vad, self.sample_rate)

        current_time = time.time()

        if has_speech:
            # Start or continue utterance
            if not self._in_utterance:
                self._in_utterance = True
                self._utterance_buffer.clear()
                print("[VAD] Speech started.", file=sys.stderr)

            self._utterance_buffer.append(pcm)
            self._last_speech_time = current_time

        else:
            # No speech in this chunk
            if self._in_utterance:
                # Check if we've been silent long enough to finalize utterance
                if (
                    self._last_speech_time is not None
                    and current_time - self._last_speech_time > self.silence_threshold
                ):
                    print("[VAD] Speech ended. Finalizing utterance.", file=sys.stderr)
                    play_beep(self.double_beep)
                    self._finalize_utterance()
                    self._in_utterance = False
                    self._utterance_buffer.clear()
                    self._last_speech_time = None

        return (in_data, pyaudio.paContinue)

    # ============================================================
    # Utterance Finalization and STT
    # ============================================================
    def _finalize_utterance(self):
        """Combine buffered PCM, run STT, and write to input.txt for Walbert."""
        if not self._utterance_buffer:
            return

        # Combine all PCM chunks
        pcm_all = np.concatenate(list(self._utterance_buffer))
        audio_float = pcm_to_float32(pcm_all)

        print("[STT] Transcribing utterance with faster-whisper...", file=sys.stderr)

        # Run faster-whisper transcription
        segments, info = self.model.transcribe(
            audio=audio_float,
            language="en",
            beam_size=5,
            vad_filter=False,  # we already did VAD
        )

        full_text = ""
        for segment in segments:
            full_text += segment.text

        full_text = full_text.strip().lower()
        print(f"[STT] Text: {full_text}", file=sys.stderr)
        
        if self.wake_word in full_text:
            play_beep(self.single_beep)
            command_text = full_text.split(self.wake_word, 1)[1].strip()
            if command_text:
                try:
                    with open('input.txt', 'w', encoding='utf-8') as f:
                        f.write(command_text)
                except Exception as e:
                    print(f"[STT] Error writing to input.txt: {e}", file=sys.stderr)
                print(f"[COMMAND] {command_text}", file=sys.stderr)
                if ENABLE_STT_TTS_LOOPBACK:
                    self.engine.say(command_text)
                    self.engine.runAndWait()
            else:
                print("[STT] Wake word detected. Awaiting command...", file=sys.stderr)
                if ENABLE_STT_TTS_LOOPBACK:
                    self.engine.say("Ready.")
                    self.engine.runAndWait()

    # ============================================================
    # Public API
    # ============================================================
    def start_stt(self):
        """Start continuous speech recognition."""
        self._running = True
        play_beep(self.single_beep)  # Single beep on start
        self.stream.start_stream()
        print("[STT] Listening for wake word and commands...", file=sys.stderr)

    def start_tts(self):
        """Read TTS commands from output.txt and speak them."""
        def speak_loop():
            print("[TTS] Ready for text input via output.txt...", file=sys.stderr)
            last_output = ""
            while self._running:
                try:
                    if os.path.exists('output.txt'):
                        with open('output.txt', 'r', encoding='utf-8') as f:
                            text = f.read().strip()
                        if text and text != last_output:
                            self.engine.say(text)
                            self.engine.runAndWait()
                            last_output = text
                        os.remove('output.txt')
                    time.sleep(0.5)
                except Exception as e:
                    print(f"[TTS] Error: {e}", file=sys.stderr)
                    time.sleep(1)

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