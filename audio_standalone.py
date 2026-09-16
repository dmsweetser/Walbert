#!/usr/bin/env python3
"""
Walbert Standalone Audio Module (Offline, Faster-Whisper + Silero VAD Edition)

- STT: faster-whisper (base) running locally
- VAD: WebRTC VAD + Silero VAD-style logic for speech detection
- Wake word: "walbert" detected from transcribed text
- TTS: pyttsx3 with espeak
- Debug: console output of audio → text, optional STT→TTS loopback

This script:
- Installs required system and Python dependencies
- Opens a microphone stream
- Uses VAD to segment speech
- Uses faster-whisper to transcribe segments
- Detects the wake word "walbert"
- After wake word, treats next utterance as a command
- Prints all recognized text to console
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
ENABLE_STT_TTS_LOOPBACK = True  # Speak back recognized text for debugging


# ============================================================
# Dependency Installation
# ============================================================
def install_system_dependencies():
    """Install system-level dependencies for audio processing."""
    if platform.system() == "Linux":
        print("[INFO] Installing system dependencies for Linux...", file=sys.stderr)
        subprocess.check_call(["sudo", "apt-get", "update"])
        subprocess.check_call(
            ["sudo", "apt-get", "install", "-y", "espeak", "ffmpeg", "portaudio19-dev"]
        )
    elif platform.system() == "Darwin":  # macOS
        print("[INFO] Installing system dependencies for macOS...", file=sys.stderr)
        subprocess.check_call(["brew", "install", "espeak", "ffmpeg", "portaudio"])
    else:
        print(
            "[ERROR] System dependency installation not supported for this OS. Please install manually.",
            file=sys.stderr,
        )
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
    install_package("systemtools")
    install_package("wheel")
    install_package("faster_whisper")
    install_package("torch")
    install_package("webrtcvad-wheels")
    install_package("pyttsx3")
    install_package("pyaudio")
    install_package("pydub")


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
        # Use CPU; you can change device="cuda" if you have GPU
        self.model = WhisperModel("base", device="cpu", compute_type="int8")

        # ----------------------------------------
        # Initialize VAD (WebRTC)
        # ----------------------------------------
        self.sample_rate = 16000
        self.vad = webrtcvad.Vad()
        # Aggressiveness: 0–3 (3 is most aggressive)
        self.vad.set_mode(2)

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

        self.wake_word = "walbert"
        self._wake_word_detected = False

        # Silence threshold after speech ends to finalize utterance
        self.silence_threshold = 1.5  # seconds

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
                    self._finalize_utterance()
                    self._in_utterance = False
                    self._utterance_buffer.clear()
                    self._last_speech_time = None

        return (in_data, pyaudio.paContinue)

    # ============================================================
    # Utterance Finalization and STT
    # ============================================================
    def _finalize_utterance(self):
        """Combine buffered PCM, run STT, handle wake word and commands."""
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

        full_text = full_text.strip()
        lower_text = full_text.lower()

        # Console output of audio → text
        if full_text:
            print(f"[STT] Text: {full_text}", file=sys.stderr)
            print(full_text, flush=True)

        # Wake word handling
        if not self._wake_word_detected:
            if self.wake_word in lower_text:
                self._wake_word_detected = True
                print(
                    f"[STT] Wake word '{self.wake_word}' detected. Awaiting command...",
                    file=sys.stderr,
                )
                if ENABLE_STT_TTS_LOOPBACK:
                    self.engine.say("Ready.")
                    self.engine.runAndWait()
            return

        # If wake word already detected, treat this utterance as a command
        if self._wake_word_detected and full_text:
            command_text = full_text
            print(f"[COMMAND] {command_text}", file=sys.stderr)
            print(command_text, flush=True)

            if ENABLE_STT_TTS_LOOPBACK:
                self.engine.say("..." + command_text)
                self.engine.runAndWait()

            # Reset wake word state after command
            self._wake_word_detected = False

    # ============================================================
    # Public API
    # ============================================================
    def start_stt(self):
        """Start continuous speech recognition."""
        self._running = True
        self.stream.start_stream()
        print("[STT] Listening for wake word and commands...", file=sys.stderr)

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
