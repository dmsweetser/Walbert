#!/usr/bin/env python3
"""
Walbert Standalone Audio Module (Offline, Faster-Whisper + WebRTC VAD Edition)

- STT: faster-whisper (base) running locally
- VAD: WebRTC VAD for speech detection
- Wake word: "computer" detected from transcribed text
- TTS: pyttsx3 with espeak
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
WAKE_WORD = "computer"
SILENCE_THRESHOLD = 1.0  # seconds of silence to end utterance
VAD_MODE = 2  # WebRTC VAD aggressiveness: 0-3
SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 30  # VAD frame duration in ms
SPEECH_THRESHOLD = 0.3  # fraction of frames that must be speech


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

        run_command(
            ["sudo", "apt-get", "update"],
            "Failed to update package lists.",
            suppress_output=True
        )

        system_packages = [
            "espeak",
            "ffmpeg",
            "portaudio19-dev",
        ]

        for package in system_packages:
            run_command(
                ["sudo", "apt-get", "install", "-y", package],
                f"Failed to install {package}.",
                suppress_output=True
            )

    elif platform.system() == "Darwin":  # macOS
        print("[INFO] Installing system dependencies for macOS...", file=sys.stderr)

        if not run_command(["brew", "--version"], "Homebrew not found."):
            print("[ERROR] Homebrew is required for macOS. Install from https://brew.sh", file=sys.stderr)
            return False

        system_packages = ["espeak", "ffmpeg", "portaudio"]

        for package in system_packages:
            run_command(
                ["brew", "install", package],
                f"Failed to install {package}.",
                suppress_output=True
            )
    else:
        print(
            "[ERROR] System dependency installation not supported for this OS. "
            "Please install: espeak, ffmpeg, portaudio.",
            file=sys.stderr,
        )
        return False
    return True


def install_python_package(package):
    """Install a Python package if it's not already installed."""
    try:
        __import__(package)
        return True
    except ImportError:
        pass

    # Try importing with a hyphen replaced by underscore
    alt_name = package.replace('-', '_')
    if alt_name != package:
        try:
            __import__(alt_name)
            return True
        except ImportError:
            pass

    print(f"[INFO] Installing {package}...", file=sys.stderr)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to install {package}.", file=sys.stderr)
        return False


def check_prerequisites():
    """Check and install all prerequisites."""
    print("[INFO] Checking prerequisites...", file=sys.stderr)

    install_system_dependencies()

    python_packages = [
        "wheel",
        "faster-whisper",
        "torch",
        "webrtcvad",
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
try:
    from faster_whisper import WhisperModel
except ImportError:
    print("[ERROR] faster-whisper not available. STT will not work.", file=sys.stderr)
    WhisperModel = None

try:
    import webrtcvad
except ImportError:
    print("[ERROR] webrtcvad not available. VAD will not work.", file=sys.stderr)
    webrtcvad = None

try:
    import pyaudio
except ImportError:
    print("[ERROR] pyaudio not available. Audio capture will not work.", file=sys.stderr)
    pyaudio = None

try:
    import pyttsx3
except ImportError:
    print("[ERROR] pyttsx3 not available. TTS will not work.", file=sys.stderr)
    pyttsx3 = None

try:
    from pydub import AudioSegment
    from pydub.playback import play
    from pydub.generators import Sine
except ImportError:
    print("[ERROR] pydub not available. Audio feedback will not work.", file=sys.stderr)
    AudioSegment = None
    play = None
    Sine = None


# ============================================================
# Helper Functions
# ============================================================

def pcm_to_float32(pcm: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 normalized to [-1, 1]."""
    return pcm.astype(np.float32) / 32768.0


def is_speech_webrtc(pcm: np.ndarray, vad: 'webrtcvad.Vad', sample_rate: int) -> bool:
    """
    Use WebRTC VAD to determine if the PCM chunk contains speech.
    Processes the chunk in VAD frame-sized pieces.
    """
    if len(pcm) == 0:
        return False

    n_samples_per_frame = int(sample_rate * CHUNK_DURATION_MS / 1000)
    total_frames = 0
    speech_frames = 0

    for offset in range(0, len(pcm) - n_samples_per_frame + 1, n_samples_per_frame):
        frame = pcm[offset:offset + n_samples_per_frame].tobytes()
        total_frames += 1
        try:
            if vad.is_speech(frame, sample_rate):
                speech_frames += 1
        except (ValueError, OverflowError):
            continue

    if total_frames == 0:
        return False

    return speech_frames / total_frames > SPEECH_THRESHOLD


def generate_beep(duration_ms: int = 100, frequency: int = 800):
    """Generate a beep sound using Pydub."""
    if Sine is None:
        return None
    beep = Sine(frequency).to_audio_segment(duration=duration_ms)
    return beep


def play_beep(beep):
    """Play a beep sound."""
    if beep and play:
        try:
            play(beep)
        except Exception:
            pass


# ============================================================
# Standalone Audio Class
# ============================================================

class StandaloneAudio:
    def __init__(self, wake_word=WAKE_WORD, silence_threshold=SILENCE_THRESHOLD,
                 vad_mode=VAD_MODE, sample_rate=SAMPLE_RATE):
        self.wake_word = wake_word
        self.silence_threshold = silence_threshold
        self.sample_rate = sample_rate

        # ----------------------------------------
        # Initialize TTS engine
        # ----------------------------------------
        self.engine = None
        if pyttsx3:
            try:
                self.engine = pyttsx3.init(driverName="espeak")
            except Exception:
                try:
                    self.engine = pyttsx3.init()
                except Exception:
                    print("[WARN] TTS engine failed to initialize.", file=sys.stderr)
        else:
            print("[WARN] pyttsx3 not available. TTS disabled.", file=sys.stderr)

        if self.engine:
            self.engine.setProperty("rate", 150)
            self.engine.setProperty("volume", 1.0)
            self.engine.setProperty("voice", "english-us")

        # ----------------------------------------
        # Initialize faster-whisper STT
        # ----------------------------------------
        self.model = None
        if WhisperModel:
            try:
                print("[INFO] Loading faster-whisper model (base)...", file=sys.stderr)
                self.model = WhisperModel("base", device="cpu", compute_type="int8")
            except Exception as e:
                print(f"[WARN] faster-whisper failed: {e}. STT disabled.", file=sys.stderr)
        else:
            print("[WARN] faster-whisper not available. STT disabled.", file=sys.stderr)

        # ----------------------------------------
        # Initialize VAD (WebRTC)
        # ----------------------------------------
        self.vad = None
        if webrtcvad:
            self.vad = webrtcvad.Vad()
            self.vad.set_mode(min(vad_mode, 3))
        else:
            print("[WARN] webrtcvad not available. VAD disabled.", file=sys.stderr)

        # ----------------------------------------
        # Audio input stream
        # ----------------------------------------
        self.pa = None
        self.stream = None
        self._audio_error_count = 0

        if pyaudio:
            try:
                self.pa = pyaudio.PyAudio()
                # List available devices for debugging
                try:
                    device_count = self.pa.get_device_count()
                    for i in range(device_count):
                        dev_info = self.pa.get_device_info_by_index(i)
                        if dev_info.get('maxInputChannels', 0) > 0:
                            print(f"[INFO] Audio input device {i}: {dev_info.get('name', 'Unknown')}", file=sys.stderr)
                except Exception:
                    pass

                self.stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=4096,
                    stream_callback=self._audio_callback,
                )
            except Exception as e:
                print(f"[WARN] Audio device error: {e}. Audio capture disabled.", file=sys.stderr)
                if self.pa:
                    self.pa.terminate()
                    self.pa = None
        else:
            print("[WARN] pyaudio not available. Audio capture disabled.", file=sys.stderr)

        # ----------------------------------------
        # State
        # ----------------------------------------
        self._running = False
        self._in_utterance = False
        self._utterance_buffer = deque()
        self._last_speech_time = None

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

        try:
            # Convert raw PCM bytes → numpy array
            pcm = np.frombuffer(in_data, dtype=np.int16)

            # VAD: determine if this chunk contains speech
            has_speech = False
            if self.vad:
                has_speech = is_speech_webrtc(pcm, self.vad, self.sample_rate)

            current_time = time.time()

            if has_speech:
                # Start or continue utterance
                if not self._in_utterance:
                    self._in_utterance = True
                    self._utterance_buffer.clear()
                    self._last_speech_time = current_time
                else:
                    self._utterance_buffer.append(pcm)
                    self._last_speech_time = current_time
            else:
                # No speech in this chunk
                if self._in_utterance:
                    if (self._last_speech_time is not None
                            and current_time - self._last_speech_time > self.silence_threshold):
                        self._finalize_utterance()
                        self._in_utterance = False
                        self._utterance_buffer.clear()
                        self._last_speech_time = None

            return (in_data, pyaudio.paContinue)
        except Exception as e:
            self._audio_error_count += 1
            if self._audio_error_count < 5:  # Log first 5 errors only
                print(f"[WARN] Audio callback error: {e}", file=sys.stderr)
            return (in_data, pyaudio.paContinue)

    # ============================================================
    # Utterance Finalization and STT
    # ============================================================
    def _finalize_utterance(self):
        """Combine buffered PCM, run STT, and write to input.txt for Walbert."""
        if not self._utterance_buffer or not self.model:
            return

        try:
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
                        self.engine.say("... Ready.")
                        self.engine.runAndWait()
        except Exception as e:
            print(f"[STT] Transcription error: {e}", file=sys.stderr)

    # ============================================================
    # Public API
    # ============================================================
    def start_stt(self):
        """Start continuous speech recognition."""
        if not self.stream:
            print("[ERROR] Audio stream not available. Check audio device.", file=sys.stderr)
            return False

        self._running = True
        play_beep(self.single_beep)  # Single beep on start
        self.stream.start_stream()
        print("[STT] Listening for wake word and commands...", file=sys.stderr)
        return True

    def start_tts(self):
        """Read TTS commands from output.txt and speak them."""
        if not self.engine:
            print("[WARN] TTS engine not available.", file=sys.stderr)
            return False

        def speak_loop():
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
        return True

    def stop(self):
        """Stop the audio module."""
        self._running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
        if self.pa:
            try:
                self.pa.terminate()
            except Exception:
                pass
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
