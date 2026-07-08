import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, call
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walbert.parser import BlockParser
from walbert.executor import BlockExecutor
from walbert.state import AgentState
from walbert.config import Config
from walbert.model_config import ModelConfig


class TestBlockParser(unittest.TestCase):
    def setUp(self):
        self.parser = BlockParser()

    def test_parse_single_block(self):
        text = "[walbert_console_response_start]Hello world[/walbert_console_response_end]"
        blocks = self.parser.parse(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "console_response")
        self.assertEqual(blocks[0]["content"], "Hello world")

    def test_parse_multiple_blocks(self):
        text = """[walbert_sql_execute_start]SELECT * FROM users[/walbert_sql_execute_end]
[walbert_awareness_start]I am learning.[/walbert_awareness_end]"""
        blocks = self.parser.parse(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["type"], "sql_execute")
        self.assertEqual(blocks[1]["type"], "awareness")

    def test_parse_with_whitespace_and_newlines(self):
        text = "[walbert_python_execute_start]\nprint('hi')\n[/walbert_python_execute_end]"
        blocks = self.parser.parse(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["content"].strip(), "print('hi')")

    def test_parse_ignores_empty_content(self):
        text = "[walbert_console_response_start][/walbert_console_response_end]"
        blocks = self.parser.parse(text)
        self.assertEqual(len(blocks), 0)


class TestBlockExecutor(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            model_configs={"model": ModelConfig("path", 2048, 512, 0.7, 0.9, 40, 0.05)},
            llama_binary_path="/fake/path",
            python_execution_timeout=30,
            temp_dir_prefix="test_"
        )
        self.db_manager = Mock()
        self.executor = BlockExecutor(self.config, self.db_manager, internet_access=False)

    def test_execute_sql(self):
        self.db_manager.execute_sql.return_value = "1 row affected"
        result = self.executor.execute({"type": "sql_execute", "content": "SELECT 1"})
        self.assertEqual(result["type"], "sql_result")
        self.assertIn("1 row affected", result["content"])

    def test_execute_awareness(self):
        result = self.executor.execute({"type": "awareness", "content": "New awareness"})
        self.assertEqual(result["type"], "awareness_update")
        self.assertEqual(result["content"], "New awareness")

    def test_execute_console_response(self):
        result = self.executor.execute({"type": "console_response", "content": "Hi"})
        self.assertEqual(result["type"], "console_response")
        self.assertEqual(result["content"], "Walbert:\nHi\n")

    def test_execute_unknown_type(self):
        result = self.executor.execute({"type": "unknown", "content": "data"})
        self.assertIsNone(result)


class TestAgentState(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            model_configs={"model": ModelConfig("path", 2048, 512, 0.7, 0.9, 40, 0.05)},
            llama_binary_path="/fake/path",
            conversation_log_dir=tempfile.mkdtemp(),
            database_path=":memory:",
            max_context_blocks=5
        )
        self.state = AgentState(self.config, None)

    def tearDown(self):
        shutil.rmtree(self.config.conversation_log_dir)

    def test_append_block_updates_context(self):
        self.state.append_block("test_block", "content1")
        self.assertEqual(len(self.state.context_blocks), 1)
        self.assertEqual(self.state.context_blocks[0]["content"], "content1")

    def test_context_truncation(self):
        for i in range(10):
            self.state.append_block("block", f"content{i}")
        self.assertEqual(len(self.state.context_blocks), 5)
        self.assertEqual(self.state.context_blocks[0]["content"], "content5")

    def test_update_awareness(self):
        self.state.update_awareness("Updated awareness text")
        self.assertEqual(self.state.awareness_text, "Updated awareness text")

    def test_get_prompt_includes_updated_state(self):
        self.state.update_awareness("Test awareness")
        self.state.append_block("test", "test content")
        prompt = self.state.get_prompt(internet_access=False)
        self.assertIn("Test awareness", prompt)
        self.assertIn("test content", prompt)
        self.assertIn("[walbert_test_start]", prompt)
        self.assertIn("[walbert_test_end]", prompt)


class TestWalbertAgent(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            model_configs={"model": ModelConfig("path", 2048, 512, 0.7, 0.9, 40, 0.05)},
            llama_binary_path="/fake/path",
            conversation_log_dir=tempfile.mkdtemp(),
            database_path=":memory:",
            max_context_blocks=10
        )
        self.agent = Mock()
        self.agent.config = self.config
        self.agent.state = AgentState(self.config, None)
        self.agent.executor = Mock()
        self.agent.parser = BlockParser()
        self.agent.logger = Mock()
        self.agent._lock = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.config.conversation_log_dir)

    def test_execute_pending_blocks_updates_state(self):
        self.agent.state.append_block("awareness", "Initial awareness")
        self.agent.executor.execute.return_value = {"type": "awareness_update", "content": "Updated awareness"}
        
        with patch.object(self.agent.state, '_sync_state'):
            self.agent._execute_pending_blocks()
            
        self.assertEqual(self.agent.state.awareness_text, "Updated awareness")
        self.agent.state._sync_state.assert_called_once()

    def test_execute_pending_blocks_appends_results(self):
        self.agent.state.append_block("python_execute", "print('hi')")
        self.agent.executor.execute.return_value = {"type": "python_result", "content": "stdout: hi"}
        
        self.agent._execute_pending_blocks()
        self.assertEqual(len(self.agent.state.context_blocks), 2)
        self.assertEqual(self.agent.state.context_blocks[1]["type"], "python_result")

    def test_prompt_reflects_execution_results(self):
        self.agent.state.append_block("sql_execute", "CREATE TABLE t")
        self.agent.executor.execute.return_value = {"type": "sql_result", "content": "OK"}
        
        self.agent._execute_pending_blocks()
        prompt = self.agent.state.get_prompt()
        self.assertIn("OK", prompt)
        self.assertIn("[walbert_sql_result_start]", prompt)


class TestIntegrationFlow(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            model_configs={"model": ModelConfig("path", 2048, 512, 0.7, 0.9, 40, 0.05)},
            llama_binary_path="/fake/path",
            conversation_log_dir=tempfile.mkdtemp(),
            database_path=":memory:",
            max_context_blocks=5
        )
        self.state = AgentState(self.config, None)
        self.parser = BlockParser()
        self.executor = BlockExecutor(self.config, Mock(), internet_access=False)

    def tearDown(self):
        shutil.rmtree(self.config.conversation_log_dir)

    def test_full_cycle_no_llm(self):
        # Simulate model returning structured blocks
        mock_model_response = """
[walbert_awareness_start]
I now know I can execute Python.
[/walbert_awareness_end]
[walbert_python_execute_start]
import os
print("ready")
[/walbert_python_execute_end]
"""
        blocks = self.parser.parse(mock_model_response)
        for block in blocks:
            self.state.append_block(block["type"], block["content"])
        
        self.executor.execute = Mock(side_effect=lambda b: {
            "awareness": {"type": "awareness_update", "content": "I now know I can execute Python."},
            "python_execute": {"type": "python_result", "content": "stdout: ready"}
        }.get(b["type"], None))
        
        # Execute pending
        pending = [b for b in self.state.context_blocks if b["type"] in {"sql_execute", "python_execute", "awareness"} and not b.get("executed", False)]
        for block in pending:
            result = self.executor.execute(block)
            if result:
                if result["type"] == "awareness_update":
                    self.state.update_awareness(result["content"])
                else:
                    self.state.append_block(result["type"], result["content"])
            block["executed"] = True
        self.state._sync_state()
        
        # Verify next prompt includes updates
        prompt = self.state.get_prompt()
        self.assertIn("I now know I can execute Python.", prompt)
        self.assertIn("stdout: ready", prompt)
        self.assertIn("[walbert_python_result_start]", prompt)


if __name__ == "__main__":
    unittest.main()
