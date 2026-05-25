"""
Test cases for WalbertAgent
"""

import unittest
import os
import tempfile
import json
from unittest.mock import patch, MagicMock
from walbert.agent import WalbertAgent
from walbert.config import Config, ModelConfig, IOConfig
from walbert.io.factory import ChannelType

class TestWalbertAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")

        model_configs = {
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
            model_configs=model_configs,
            llama_binary_path="/fake/path/llama-server",
            log_level="DEBUG"
        )

        self.io_config = IOConfig({
            "console": {"enabled": True, "require_authorization": False}
        })

        os.environ["WALBERT_TEST_MODE"] = "1"

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
        if "WALBERT_TEST_MODE" in os.environ:
            del os.environ["WALBERT_TEST_MODE"]

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    @patch('walbert.skills.manager.SkillManager')
    def test_agent_initialization(self, mock_skill, mock_model, mock_db):
        agent = WalbertAgent(self.config, self.io_config)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.config, self.config)
        self.assertEqual(agent.io_config, self.io_config)

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_start_conversation(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.start_conversation.return_value = 1
        mock_db_instance.get_schema.return_value = "test schema"
        mock_db.return_value = mock_db_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.start_conversation(ChannelType.CONSOLE)

        self.assertEqual(agent.current_conversation_id, 1)
        mock_db_instance.start_conversation.assert_called_once_with("console")
        mock_db_instance.add_message.assert_called_once()

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_end_conversation(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.start_conversation.return_value = 1
        mock_db.return_value = mock_db_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.start_conversation(ChannelType.CONSOLE)
        agent.end_conversation()

        self.assertIsNone(agent.current_conversation_id)
        mock_db_instance.end_conversation.assert_called_once_with(1, "End of conversation")

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_process_response_with_sql(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.execute_sql.return_value = "Query results:\nid\tcontent\ntest\tskill code"
        mock_db.return_value = mock_db_instance

        mock_model_instance = MagicMock()
        mock_model_instance.execute_ministral.return_value = """
        ~walbert_response_start~
        test response
        ~walbert_response_end~
        ~walbert_sql_execute_start~
        SELECT * FROM items
        ~walbert_sql_execute_end~
        """
        mock_model.return_value = mock_model_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.current_conversation_id = 1

        response = agent.process_response(
            "~walbert_response_start~\ntest\n~walbert_response_end~\n~walbert_sql_execute_start~\nSELECT * FROM items\n~walbert_sql_execute_end~",
            ChannelType.CONSOLE
        )

        self.assertEqual(response["response"], "test")
        self.assertEqual(response["sql_result"], "Query results:\nid\tcontent\ntest\tskill code")

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_process_response_with_skill(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.execute_sql.return_value = "Query results:\nid\tcontent\ntest\tskill code"
        mock_db.return_value = mock_db_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.current_conversation_id = 1

        with patch.object(agent.skill_manager, 'execute_skill') as mock_execute:
            mock_execute.return_value = "skill output"
            response = agent.process_response(
                "~walbert_skill_execute_start~\ntest_skill\n~walbert_skill_execute_end~",
                ChannelType.CONSOLE
            )

            self.assertEqual(response["skill_result"], "skill output")

    @patch('walbert.database.manager.DatabaseManager')
    @patch('walbert.models.manager.ModelManager')
    def test_build_conversation_context(self, mock_model, mock_db):
        mock_db_instance = MagicMock()
        mock_db_instance.cursor.execute.return_value.fetchall.return_value = [
            ("user", "test message"),
            ("assistant", "test response")
        ]
        mock_db.return_value = mock_db_instance

        agent = WalbertAgent(self.config, self.io_config)
        agent.current_conversation_id = 1

        context = agent.build_conversation_context()
        self.assertIn("User: test message", context)
        self.assertIn("Assistant: test response", context)

if __name__ == "__main__":
    unittest.main()
