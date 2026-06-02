"""
Text-to-speech implementation using offline models
"""

import os
import logging
from pyttsx3 import Engine

logger = logging.getLogger('walbert.tts')

class TextToSpeech:
    """Text-to-speech using offline pyttsx3 engine"""

    def __init__(self):
        self.engine = None
        self.initialize()

    def initialize(self):
        """Initialize TTS engine"""
        try:
            self.engine = Engine()
            self.engine.setProperty('rate', 150)  # Speed of speech
            self.engine.setProperty('volume', 0.9)  # Volume level (0.0 to 1.0)
            logger.info("Text-to-speech engine initialized")
        except Exception as e:
            logger.error(f"Error initializing text-to-speech: {e}")
            self.engine = None

    def speak(self, text: str):
        """Convert text to speech"""
        if not self.engine:
            logger.warning("TTS engine not available")
            return False

        if not text or not text.strip():
            return True

        try:
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}")
            return False

    def stop(self):
        """Stop current speech"""
        if self.engine:
            self.engine.stop()
            logger.debug("Stopped current speech")
