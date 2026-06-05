"""
Speech-to-text implementation using offline models
"""

import os
import logging
import threading
import queue
import time
from vosk import Model, KaldiRecognizer
import sounddevice as sd
import numpy as np

logger = logging.getLogger('walbert.stt')

class SpeechToText:
    """Speech-to-text using offline Vosk model"""

    def __init__(self):
        self.model = None
        self.recognizer = None
        self.stream = None
        self.listening = False
        self.buffer = queue.Queue()
        self.input_started = False
        self.input_buffer = ""

    def initialize(self):
        """Initialize STT engine"""
        try:
            # Load Vosk model
            model_path = "instance/models/vosk-model-small-en-us-0.15"
            if not os.path.exists(model_path):
                logger.error(f"Vosk model not found at {model_path}")
                return False

            # Suppress Vosk logging
            os.environ['GLOG_minloglevel'] = '2'
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, 16000)
            logger.info("Speech-to-text engine initialized")
            return True
        except Exception as e:
            logger.error(f"Error initializing speech-to-text: {e}")
            return False

    def callback(self, indata, frames, time, status):
        """Audio callback for recording"""
        if status:
            logger.warning(f"Audio status: {status}")
        self.buffer.put(bytes(indata))

    def start_listening(self, start_event):
        """Start continuous listening for voice commands"""
        if not self.initialize():
            logger.error("Failed to initialize STT engine")
            return

        # Wait for start signal
        start_event.wait()

        self.listening = True
        logger.info("Speech-to-text listening started")

        try:
            with sd.RawInputStream(samplerate=16000, dtype='int16',
                                   channels=1, callback=self.callback, blocksize=8000):
                while self.listening:
                    if self.buffer.qsize() > 0:
                        data = self.buffer.get_nowait()
                        if self.recognizer.AcceptWaveform(data):
                            result = self.recognizer.Result()
                            text = eval(result)["text"].strip()
                            if text:
                                # Check for "Hey Walbert" to start input
                                if text.lower().startswith("hey walbert"):
                                    logger.info("Voice input activated")
                                    self.input_started = True
                                    self.input_buffer = text.replace("hey walbert", "").strip()
                                elif self.input_started:
                                    self.input_buffer += " " + text
                                    # Check for "Thanks" to end input
                                    if "thanks" in text.lower():
                                        final_input = self.input_buffer.strip()
                                        logger.info(f"Voice input received: {final_input}")
                                        # Send to main input queue (would need to be passed in)
                                        self.input_started = False
                                        self.input_buffer = ""
                    time.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in speech-to-text listening: {e}")
        finally:
            self.listening = False
            logger.info("Speech-to-text listening stopped")

    def resume_listening(self):
        """Resume listening"""
        self.listening = True
        logger.info("Speech-to-text listening resumed")

    def pause_listening(self):
        """Pause listening"""
        self.listening = False
        logger.info("Speech-to-text listening paused")

    def stop(self):
        """Stop listening"""
        self.listening = False
        logger.info("Speech-to-text stopped")
