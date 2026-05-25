"""
Test cases for ModelManager
"""

import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
from walbert.models.manager import ModelManager
from walbert.config import Config, ModelConfig

class TestModelManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        model_configs = {
            "ministral": ModelConfig(
                model_path=os.path.join(self.temp_dir, "ministral.gguf"),
                context_size=2048,
                output_tokens=512,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                min_p=0.05
            ),
            "devstral": ModelConfig(
                model_path=os.path.join(self.temp_dir, "devstral.gguf"),
                context_size=4096,
                output_tokens=1024,
                temperature=0.8,
                top_p=0.95,
                top_k=50,
                min_p=0.1
            )
        }

        self.config = Config(
            model_configs=model_configs,
            llama_binary_path=os.path.join(self.temp_dir, "llama-server"),
            mmproj_path=os.path.join(self.temp_dir, "mmproj.gguf"),
            log_level="DEBUG"
        )

        # Create fake files
        for path in [
            self.config.model_configs["ministral"].model_path,
            self.config.model_configs["devstral"].model_path,
            self.config.llama_binary_path,
            self.config.mmproj_path
        ]:
            with open(path, 'w') as f:
                f.write("fake content")

    def tearDown(self):
        for path in [
            self.config.model_configs["ministral"].model_path,
            self.config.model_configs["devstral"].model_path,
            self.config.llama_binary_path,
            self.config.mmproj_path
        ]:
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    @patch('subprocess.Popen')
    @patch('requests.get')
    def test_model_manager_initialization(self, mock_get, mock_popen):
        mock_get.return_value.status_code = 200
        mock_popen.return_value = MagicMock()

        manager = ModelManager(self.config)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.config, self.config)

    @patch('subprocess.Popen')
    @patch('requests.get')
    @patch('requests.post')
    def test_execute_ministral(self, mock_post, mock_get, mock_popen):
        mock_get.return_value.status_code = 200
        mock_popen.return_value = MagicMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "test response"}}]}

        manager = ModelManager(self.config)
        result = manager.execute_ministral("test prompt")
        self.assertEqual(result, "test response")

    @patch('subprocess.Popen')
    @patch('requests.get')
    @patch('requests.post')
    def test_execute_devstral(self, mock_post, mock_get, mock_popen):
        mock_get.return_value.status_code = 200
        mock_popen.return_value = MagicMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "test response"}}]}

        manager = ModelManager(self.config)
        result = manager.execute_devstral("test prompt")
        self.assertEqual(result, "test response")

    @patch('subprocess.Popen')
    @patch('requests.get')
    def test_shutdown(self, mock_get, mock_popen):
        mock_get.return_value.status_code = 200
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        manager = ModelManager(self.config)
        manager.shutdown()

        mock_process.terminate.assert_called()
        mock_process.wait.assert_called()

if __name__ == "__main__":
    unittest.main()
