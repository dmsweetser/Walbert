#!/usr/bin/env python3
"""
Unit tests for model management
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walbert.models.manager import ModelManager
from walbert.config import Config, ModelConfig

class TestModelManager(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            model_configs={
                'ministral': ModelConfig(
                    model_path="test_primary.gguf",
                    context_size=2048,
                    output_tokens=512,
                    temperature=0.7,
                    top_p=0.9,
                    top_k=40,
                    min_p=0.05
                ),
                'devstral': ModelConfig(
                    model_path="test_devstral.gguf",
                    context_size=4096,
                    output_tokens=1024,
                    temperature=0.8,
                    top_p=0.95,
                    top_k=50,
                    min_p=0.1
                )
            },
            llama_binary_path="test_llama",
            mmproj_path="test_mmproj.gguf",
            log_level="DEBUG"
        )
        with patch('os.path.isfile', return_value=True):
            self.model_manager = ModelManager(self.config)

    @patch('os.path.isfile')
    def test_validate_binaries_success(self, mock_isfile):
        mock_isfile.return_value = True
        try:
            self.model_manager.validate_binaries()
        except Exception:
            self.fail("validate_binaries() raised an exception unexpectedly")

    @patch('os.path.isfile')
    def test_validate_binaries_failure(self, mock_isfile):
        mock_isfile.return_value = False
        with self.assertRaises(FileNotFoundError):
            self.model_manager.validate_binaries()

    @patch('subprocess.run')
    def test_execute_model_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="test output", returncode=0)
        result = self.model_manager.execute_model("test_model.gguf", "test prompt")
        self.assertEqual(result, "test output")

    @patch('subprocess.run')
    def test_execute_model_failure(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="error", returncode=1)
        with self.assertRaises(RuntimeError):
            self.model_manager.execute_model("test_model.gguf", "test prompt")

    @patch('subprocess.run')
    def test_execute_ministral(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ministral output", returncode=0)
        result = self.model_manager.execute_ministral("test prompt", "test_mmproj.gguf")
        self.assertEqual(result, "ministral output")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("--mmproj", args)
        self.assertIn("test_mmproj.gguf", args)

    @patch('subprocess.run')
    def test_execute_devstral(self, mock_run):
        mock_run.return_value = MagicMock(stdout="devstral output", returncode=0)
        result = self.model_manager.execute_devstral("test prompt")
        self.assertEqual(result, "devstral output")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertNotIn("--mmproj", args)

if __name__ == '__main__':
    unittest.main()
