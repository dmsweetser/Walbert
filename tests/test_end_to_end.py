#!/usr/bin/env python3
"""
End-to-end test for Walbert agent system
"""

import unittest
import os
import tempfile
import shutil
import json
from unittest.mock import patch, MagicMock
from walbert import WalbertAgent, Config, IOConfig, ModelConfig
from walbert.io.factory import ChannelType

class TestWalbertEndToEnd(unittest.TestCase):
    """End-to-end test for Walbert agent"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        os.makedirs('instance', exist_ok=True)

        # Create minimal config
        self.config_data = {
            "model_configs": {
                "ministral": {
                    "model_path": "/tmp/test_ministral.gguf",
                    "context_size": 2048,
                    "output_tokens": 512,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "min_p": 0.05
                },
                "devstral": {
                    "model_path": "/tmp/test_devstral.gguf",
                    "context_size": 4096,
                    "output_tokens": 1024,
                    "temperature": 0.8,
                    "top_p": 0.95,
                    "top_k": 50,
                    "min_p": 0.1
                }
            },
            "llama_binary_path": "/tmp/llama-server",
            "log_level": "DEBUG"
        }

        with open('instance/config.json', 'w') as f:
            json.dump(self.config_data, f)

        # Create minimal io_config
        self.io_config_data = {
            "console": {
                "enabled": True,
                "require_authorization": False
            },
            "serial": {
                "enabled": False,
                "require_authorization": True
            },
            "python_code": {
                "enabled": False,
                "require_authorization": True
            }
        }

        with open('instance/io_config.json', 'w') as f:
            json.dump(self.io_config_data, f)

        # Create mock model configs
        model_configs = {
            'ministral': ModelConfig(**self.config_data['model_configs']['ministral']),
            'devstral': ModelConfig(**self.config_data['model_configs']['devstral'])
        }

        self.config = Config(
            model_configs=model_configs,
            llama_binary_path=self.config_data['llama_binary_path']
        )

        self.io_config = IOConfig(io_layers=self.io_config_data)

    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    @patch('walbert.models.manager.subprocess.Popen')
    @patch('walbert.models.manager.requests.post')
    @patch('walbert.database.manager.sqlite3.connect')
    def test_end_to_end_flow(self, mock_connect, mock_post, mock_popen):
        """Test complete end-to-end flow"""
        # Setup mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        # Setup mock model responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": """~walbert_response_start~
Hello! How can I help you today?
~walbert_response_channel_start~
console
~walbert_conversation_complete_start~
NO
~walbert_should_query_datastore_start~
NO"""
                }
            }]
        }
        mock_post.return_value = mock_response

        # Setup mock subprocess
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Initialize agent
        agent = WalbertAgent(self.config, self.io_config)

        # Test conversation flow
        with patch('builtins.input', side_effect=['test input', 'exit']):
            with patch('builtins.print') as mock_print:
                agent.run()

                # Verify conversation was started
                mock_cursor.execute.assert_any_call(
                    "INSERT INTO conversations (channel) VALUES (?)",
                    ("console",)
                )

                # Verify messages were added
                mock_cursor.execute.assert_any_call(
                    "INSERT INTO messages (conversation_id, content, sender) VALUES (?, ?, ?)",
                    (1, "test input", "user")
                )

                # Verify response was printed
                mock_print.assert_called_with("Hello! How can I help you today?")

    @patch('walbert.models.manager.subprocess.Popen')
    @patch('walbert.models.manager.requests.post')
    @patch('walbert.database.manager.sqlite3.connect')
    def test_sql_execution_flow(self, mock_connect, mock_post, mock_popen):
        """Test SQL execution flow"""
        # Setup mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        # Setup mock model responses
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {
            "choices": [{
                "message": {
                    "content": """~walbert_response_start~
I need to check something in the database.
~walbert_response_channel_start~
console
~walbert_conversation_complete_start~
NO
~walbert_should_query_datastore_start~
YES
~walbert_sql_execute_start~
SELECT * FROM items WHERE type='skill'"""
                }
            }]
        }

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {
            "choices": [{
                "message": {
                    "content": """~walbert_response_start~
Found 2 skills in the database.
~walbert_response_channel_start~
console
~walbert_conversation_complete_start~
YES"""
                }
            }]
        }

        mock_post.side_effect = [mock_response1, mock_response2]

        # Setup mock subprocess
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Setup mock SQL execution result
        mock_cursor.fetchall.return_value = [
            (1, "def test_skill(): return 'test'", "skill")
        ]

        # Initialize agent
        agent = WalbertAgent(self.config, self.io_config)

        with patch('builtins.input', side_effect=['test input', 'exit']):
            with patch('builtins.print') as mock_print:
                agent.run()

                # Verify SQL was executed
                mock_cursor.execute.assert_any_call(
                    "SELECT * FROM items WHERE type='skill'"
                )

                # Verify final response was printed
                mock_print.assert_called_with("Found 2 skills in the database.")

    @patch('walbert.models.manager.subprocess.Popen')
    @patch('walbert.database.manager.sqlite3.connect')
    def test_skill_execution_flow(self, mock_connect, mock_popen):
        """Test skill execution flow"""
        # Setup mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        # Setup mock subprocess for model
        mock_model_process = MagicMock()
        mock_model_process.wait.return_value = 0
        mock_popen.return_value = mock_model_process

        # Setup mock skill execution
        with patch('walbert.skills.manager.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Skill executed successfully"
            mock_run.return_value = mock_result

            # Setup mock model response
            with patch('walbert.models.manager.requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": """~walbert_response_start~
I will execute a skill now.
~walbert_response_channel_start~
console
~walbert_conversation_complete_start~
NO
~walbert_should_query_datastore_start~
YES
~walbert_sql_execute_start~
SELECT content FROM items WHERE type='skill' AND content LIKE '%test_skill%'
~walbert_skill_execute_start~
test_skill"""
                        }
                    }]
                }
                mock_post.return_value = mock_response

                # Setup mock SQL result
                mock_cursor.fetchall.return_value = [
                    (1, "def test_skill(): return 'test result'", "skill")
                ]

                # Initialize agent
                agent = WalbertAgent(self.config, self.io_config)

                with patch('builtins.input', side_effect=['test input', 'exit']):
                    with patch('builtins.print') as mock_print:
                        agent.run()

                        # Verify skill was executed
                        mock_run.assert_called_once()

                        # Verify response was printed
                        mock_print.assert_called_with("I will execute a skill now.")

    @patch('walbert.models.manager.subprocess.Popen')
    @patch('walbert.database.manager.sqlite3.connect')
    def test_conversation_completion(self, mock_connect, mock_popen):
        """Test conversation completion flow"""
        # Setup mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        # Setup mock subprocess
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Setup mock model response
        with patch('walbert.models.manager.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": """~walbert_response_start~
Goodbye!
~walbert_response_channel_start~
console
~walbert_conversation_complete_start~
YES"""
                    }
                }]
            }
            mock_post.return_value = mock_response

            # Initialize agent
            agent = WalbertAgent(self.config, self.io_config)

            with patch('builtins.input', side_effect=['test input', 'exit']):
                with patch('builtins.print') as mock_print:
                    agent.run()

                    # Verify conversation was ended
                    mock_cursor.execute.assert_any_call(
                        "UPDATE conversations SET end_time = CURRENT_TIMESTAMP, summary = ? WHERE id = ?",
                        ("End of conversation", 1)
                    )

                    # Verify new conversation was started
                    mock_cursor.execute.assert_any_call(
                        "INSERT INTO conversations (channel) VALUES (?)",
                        ("console",)
                    )

if __name__ == '__main__':
    unittest.main()
