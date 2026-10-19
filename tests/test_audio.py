"""Tests for the audio module."""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAudioHelpers:
    """Test audio helper functions."""

    def test_pcm_to_float32(self):
        import numpy as np
        # Import after sys.path is set
        from audio_standalone import pcm_to_float32
        pcm = np.array([0, 32767, -32768], dtype=np.int16)
        result = pcm_to_float32(pcm)
        assert result[0] == 0.0
        assert result[1] == pytest.approx(1.0, abs=0.01)
        assert result[2] == pytest.approx(-1.0, abs=0.01)

    def test_generate_beep(self):
        from audio_standalone import generate_beep
        beep = generate_beep(duration_ms=100, frequency=800)
        # beep is a pydub AudioSegment or None
        assert beep is None or hasattr(beep, 'raw_data')

    def test_play_beep_none(self):
        from audio_standalone import play_beep
        # Should not crash with None
        play_beep(None)

    def test_is_speech_webrtc_no_vad(self):
        """Test when VAD is None."""
        from audio_standalone import is_speech_webrtc
        import numpy as np
        # Should not crash
        result = is_speech_webrtc(np.array([0], dtype=np.int16), None, 16000)
        assert result is False

    def test_is_speech_webrtc_empty(self):
        from audio_standalone import is_speech_webrtc
        import numpy as np
        result = is_speech_webrtc(np.array([], dtype=np.int16), MagicMock(), 16000)
        assert result is False


class TestStandaloneAudio:
    """Test the StandaloneAudio class with mocked dependencies."""

    @pytest.fixture
    def mock_audio_deps(self):
        """Mock all audio dependencies before importing audio_standalone."""
        # Mock at the source level since audio_standalone imports these inside functions
        with patch.dict('sys.modules', {
            'faster_whisper': MagicMock(),
            'webrtcvad': MagicMock(),
            'pyaudio': MagicMock(),
            'pyttsx3': MagicMock(),
            'pydub': MagicMock(),
            'pydub.playback': MagicMock(),
            'pydub.generators': MagicMock(),
            'pydub.generators.Sine': MagicMock(),
        }):
            # Setup pyaudio mock
            import sys
            mock_pa = sys.modules['pyaudio']
            mock_pa.PyAudio.return_value = MagicMock()
            mock_pa.PyAudio.return_value.get_device_count.return_value = 1
            mock_pa.PyAudio.return_value.get_device_info_by_index.return_value = {
                'name': 'Test Device',
                'maxInputChannels': 1
            }
            mock_pa.paInt16 = 0
            mock_pa.paContinue = 1
            
            # Setup pyttsx3 mock
            mock_tts = sys.modules['pyttsx3']
            mock_tts.init.return_value = MagicMock()
            
            yield {
                'tts': mock_tts,
                'pa': mock_pa,
            }

    @pytest.fixture
    def audio(self, mock_audio_deps):
        """Create a StandaloneAudio with all dependencies mocked."""
        from audio_standalone import StandaloneAudio
        audio = StandaloneAudio()
        audio.pa = mock_audio_deps['pa'].PyAudio.return_value
        audio.stream = MagicMock()
        return audio

    def test_init(self, audio):
        assert audio.wake_word == "computer"
        assert audio.silence_threshold == 1.0
        assert audio._running is False
        assert audio._in_utterance is False

    def test_start_stt_no_stream(self):
        """Test start_stt when stream is not available."""
        from audio_standalone import StandaloneAudio
        with patch.dict('sys.modules', {'pyaudio': MagicMock()}):
            import sys
            sys.modules['pyaudio'].PyAudio.return_value = None
            audio = StandaloneAudio()
            result = audio.start_stt()
            assert result is False

    def test_start_tts_no_engine(self):
        """Test start_tts when engine is not available."""
        from audio_standalone import StandaloneAudio
        with patch.dict('sys.modules', {'pyttsx3': MagicMock()}):
            import sys
            sys.modules['pyttsx3'].init.side_effect = Exception("Failed")
            audio = StandaloneAudio()
            result = audio.start_tts()
            assert result is False

    def test_stop(self, audio):
        audio.stream = MagicMock()
        audio.pa = MagicMock()
        audio.stop()
        assert audio._running is False

    def test_finalize_utterance_no_buffer(self, audio):
        """Test _finalize_utterance with empty buffer."""
        audio._utterance_buffer.clear()
        audio._finalize_utterance()  # Should not crash

    def test_finalize_utterance_no_model(self, audio):
        """Test _finalize_utterance without model."""
        audio.model = None
        audio._utterance_buffer.append(b"test data")
        audio._finalize_utterance()  # Should not crash

    def test_audio_callback_not_running(self, audio):
        """Test audio callback when not running."""
        pytest.skip("Audio callback requires pyaudio which isn't installed")

    def test_audio_callback_error_handling(self, audio):
        """Test that audio callback handles errors gracefully."""
        pytest.skip("Audio callback requires pyaudio which isn't installed")

    def test_wake_word_detection(self, audio, tmp_path):
        """Test wake word detection and input.txt writing."""
        pytest.skip("Requires faster-whisper model which isn't installed")

    def test_configurable_parameters(self):
        """Test that audio parameters are configurable."""
        with patch.dict('sys.modules', {
            'faster_whisper': MagicMock(),
            'webrtcvad': MagicMock(),
            'pyaudio': MagicMock(),
            'pyttsx3': MagicMock(),
            'pydub': MagicMock(),
            'pydub.playback': MagicMock(),
            'pydub.generators': MagicMock(),
        }):
            import sys
            mock_pa = sys.modules['pyaudio']
            mock_pa.PyAudio.return_value = MagicMock()
            mock_pa.PyAudio.return_value.get_device_count.return_value = 1
            mock_pa.PyAudio.return_value.get_device_info_by_index.return_value = {
                'name': 'Test',
                'maxInputChannels': 1
            }
            mock_pa.paInt16 = 0
            mock_pa.paContinue = 1
            
            mock_tts = sys.modules['pyttsx3']
            mock_tts.init.return_value = MagicMock()
            
            from audio_standalone import StandaloneAudio
            audio = StandaloneAudio(
                wake_word="hey",
                silence_threshold=2.0,
                vad_mode=3
            )
            assert audio.wake_word == "hey"
            assert audio.silence_threshold == 2.0
