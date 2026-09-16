#!/usr/bin/env python3
"""
Walbert Standalone Audio Module
Handles STT and TTS independently, hooking into console I/O via standard streams.
Run this script in a separate terminal or background process.
STT output is printed to stdout. TTS input is read from stdin.
"""

import sys
import os
import threading
import time
import speech_recognition as sr
import pyttsx3

class StandaloneAudio:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 1.0)
        self._running = False
        self._tts_queue = []
        self._tts_lock = threading.Lock()

    def start_stt(self):
        """Start continuous speech recognition in a background thread."""
        def listen_loop():
            microphone = sr.Microphone()
            with microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                print("[STT] Listening...", file=sys.stderr)
                while self._running:
                    try:
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                        text = self.recognizer.recognize_google(audio)
                        text = text.strip().lower()
                        if text:
                            print(text, flush=True)
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError as e:
                        print(f"[STT] Error: {e}", file=sys.stderr)
                        break
                    except Exception as e:
                        print(f"[STT] Unexpected error: {e}", file=sys.stderr)
                        break

        self._running = True
        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()

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
        self._running = False
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