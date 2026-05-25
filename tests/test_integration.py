"""
Integration tests for Walbert system
"""

import unittest
import os
import tempfile
import json
from unittest.mock import patch, MagicMock
from walbert.agent import WalbertAgent
from walbert.config import Config, ModelConfig, IOConfig
from walbert.io.factory import ChannelType

class TestWalbertIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Create test config files
        os.makedirs('instance', exist_ok=True)

        config_data = {
            "model_configs": {
                "ministral": {
                    "model_path": "/fake/path/ministral.gguf",
                    "context_size": 2048,
                    "output_tokens": 512,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "min_p": 0.05
                },
                "devstral": {
                    "model_path": "/fake/path/devstral.gguf",
                    "context_size": 4096,
                    "output_tokens": 1024,
                    "temperature": 0.8,
                    "top_p": 0.95,
                    "top_k": 50,
                    "min_p": 0.1
                }
            },
            "llama_binary_path": "/fake/path/llama-server",
            "log_level": "DEBUG"
        }

        with open('instance/config.json', 'w') as f:
            json.dump(config_data, f)

        io_config_data = {
            "console": {
                "enabled": True,
                "require_authorization": False
            }
        }

        with open('instance/io_config.json', 'w') as f:
            json.dump(io_config_data, f)

        self.model_configs = {
            "ministral": ModelConfig(
                model_path="/fake/path/ministral.gguf",
                context_size=2048,
                output_tokens=512,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                min_p=0.05
            ),
            "devstral": ModelConfig(
                model_path="/fake/path/devstral.gguf",
                context_size=4096,
                output_tokens=1024,
                temperature=0.8,
                top_p=0.95,
                top_k=50,
                min_p=0.1
            )
        }

        self.config = Config(
            model_configs=self.model_configs,
            llama_binary_path="/fake/path/llama-server",
            log_level="DEBUG"
        )

        self.io_config = IOConfig(io_config_data)

    def tearDown(self):
        if os.path.exists('instance/config.json'):
            os.remove('instance/config.json')
        if os.path.exists('instance/io_config.json'):
            os.remove('instance/io_config.json')
        if os.path.exists('instance'):
            os.rmdir('instance')
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    @patch('walbert.skills.manager.SkillManager')
    def test_full_agent_flow(self, mock_skill, mock_model, mock_db):
        # Setup mocks
        mock_db_instance = MagicMock()
        mock_db_instance.start_conversation.return_value = 1
        mock_db_instance.get_schema.return_value = "test schema"
        mock_db_instance.execute_sql.return_value = "Query results:\nid\tcontent\ntest\tskill code"
        mock_db.return_value = mock_db_instance

        mock_model_instance = MagicMock()
        mock_model_instance.execute_ministral.return_value = """
        ~walbert_response_start~
        Hello, how can I help you?
        ~walbert_response_end~
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        """
        mock_model.return_value = mock_model_instance

        mock_skill_instance = MagicMock()
        mock_skill_instance.execute_skill.return_value = "skill executed successfully"
        mock_skill.return_value = mock_skill_instance

        # Create agent
        agent = WalbertAgent(self.config, self.io_config)

        # Test conversation flow
        agent.start_conversation(ChannelType.CONSOLE)
        self.assertEqual(agent.current_conversation_id, 1)

        # Test response processing
        response = agent.process_response(
            "~walbert_response_start~\nHello\n~walbert_response_end~",
            ChannelType.CONSOLE
        )
        self.assertEqual(response["response"], "Hello")

        # Test conversation context building
        mock_db_instance.cursor.execute.return_value.fetchall.return_value = [
            ("user", "test message"),
            ("assistant", "test response")
        ]
        context = agent.build_conversation_context()
        self.assertIn("User: test message", context)

        # Test conversation ending
        agent.end_conversation()
        self.assertIsNone(agent.current_conversation_id)
        mock_db_instance.end_conversation.assert_called_once_with(1, "End of conversation")

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_skill_execution_flow(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.start_conversation.return_value = 1
        mock_db_instance.get_schema.return_value = "test schema"
        mock_db_instance.execute_sql.return_value = "Query results:\nid\tcontent\ntest\tprint('hello')"
        mock_db.return_value = mock_db_instance

        mock_model_instance = MagicMock()
        mock_model_instance.execute_ministral.return_value = """
        ~walbert_response_start~
        Executing skill...
        ~walbert_response_end~
        ~walbert_skill_execute_start~
        hello_skill
        ~walbert_skill_execute_end~
        """
        mock_model.return_value = mock_model_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.start_conversation(ChannelType.CONSOLE)

        with patch.object(agent.skill_manager, 'execute_skill') as mock_execute:
            mock_execute.return_value = "hello from skill"
            response = agent.process_response(
                "~walbert_skill_execute_start~\nhello_skill\n~walbert_skill_execute_end~",
                ChannelType.CONSOLE
            )

            self.assertEqual(response["skill_result"], "hello from skill")
            mock_execute.assert_called_once_with("print('hello')")

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_sql_execution_flow(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.start_conversation.return_value = 1
        mock_db_instance.get_schema.return_value = "test schema"
        mock_db_instance.execute_sql.return_value = "Query results:\nid\tcontent\n1\ttest content"
        mock_db.return_value = mock_db_instance

        mock_model_instance = MagicMock()
        mock_model_instance.execute_ministral.return_value = """
        ~walbert_response_start~
        Here are your items
        ~walbert_response_end~
        ~walbert_sql_execute_start~
        SELECT * FROM items
        ~walbert_sql_execute_end~
        """
        mock_model.return_value = mock_model_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.start_conversation(ChannelType.CONSOLE)

        response = agent.process_response(
            "~walbert_sql_execute_start~\nSELECT * FROM items\n~walbert_sql_execute_end~",
            ChannelType.CONSOLE
        )

        self.assertEqual(response["sql_result"], "Query results:\nid\tcontent\n1\ttest content")
        mock_db_instance.execute_sql.assert_called_once_with("SELECT * FROM items")

if __name__ == "__main__":
    unittest.main()
