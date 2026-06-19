"""
End-to-end test for revised WalbertAgent with block-based, auditable context chain.
Validates block parsing, execution, context management, and error handling.
Fixed: Uses MockDatabaseManager and patches Python execution to avoid environment-specific issues.
"""

import os
import sys
import unittest
import tempfile
import shutil
import json
import queue
import threading
import time
from unittest.mock import patch, MagicMock
from walbert.agent import WalbertAgent
from walbert.config import Config, ModelConfig


class MockDatabaseManager:
    """Mock DatabaseManager for testing"""
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = MagicMock()
        self.cursor = MagicMock()

    def connect(self):
        """Mock database connection"""
        pass

    def get_schema(self):
        """Mock schema retrieval"""
        return "Mock Schema: Table: items"

    def execute_sql(self, sql):
        """Mock SQL execution"""
        if "CREATE TABLE" in sql:
            return "Table created successfully"
        elif "INSERT INTO" in sql:
            return "Row inserted successfully"
        elif "SELECT" in sql:
            return [{"id": 1, "name": "test", "value": 1.0}]
        else:
            return "Mock SQL Result"


class MockModelManager:
    """Mock ModelManager for testing block-based WalbertAgent"""
    def __init__(self, config):
        self.config = config
        self.server_started = True
        self.responses = []
        self.current_response = 0

    def start_server_thread(self):
        """Mock server start"""
        self.server_started = True

    def wait_for_server(self, timeout=None):
        """Mock server ready"""
        return self.server_started

    def execute_model(self, prompt, callback=None, interrupt_event=None):
        """Return predefined responses"""
        if self.current_response >= len(self.responses):
            return ""

        response = self.responses[self.current_response]
        self.current_response += 1

        if callback:
            for chunk in response.split():
                callback(chunk + " ")
                if interrupt_event and interrupt_event.is_set():
                    break
                time.sleep(0.01)

        return response

    def shutdown(self):
        """Mock shutdown"""
        self.server_started = False


class TestWalbertAgent(unittest.TestCase):
    """End-to-end test for block-based WalbertAgent"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.conversation_dir = os.path.join(self.temp_dir, "conversations")

        # Create minimal config
        model_config = ModelConfig(
            model_path="/fake/path/model.gguf",
            context_size=2048,
            output_tokens=512,
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            min_p=0.05
        )

        self.config = Config(
            model_configs={"model": model_config},
            llama_binary_path="/fake/path/llama-server",
            mmproj_path="",
            log_level="DEBUG",
            conversation_log_dir=self.conversation_dir,
            database_path=self.db_path,
            be_presbyterian=False
        )

        # Create mock model manager
        self.mock_manager = MockModelManager(self.config)

        # Patch ModelManager and DatabaseManager
        self.patcher_model = patch('walbert.agent.ModelManager', return_value=self.mock_manager)
        self.patcher_db = patch('walbert.agent.DatabaseManager', return_value=MockDatabaseManager(self.db_path))
        self.mock_model_manager = self.patcher_model.start()
        self.mock_db_manager = self.patcher_db.start()

        # Create agent
        self.agent = WalbertAgent(self.config, self.mock_manager)

        # Set up test responses
        self._setup_test_responses()

    def tearDown(self):
        """Clean up test environment"""
        self.agent.shutdown()
        self.patcher_model.stop()
        self.patcher_db.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _setup_test_responses(self):
        """Set up test responses for the mock model using new block format"""
        # Response 1: Simple console response
        self.mock_manager.responses.append("""
[walbert_console_response_start]
Hello! How can I help you today?
[walbert_console_response_end]

[walbert_summary_start]
Provided greeting to user
[walbert_summary_end]
""")

        # Response 2: SQL execution
        self.mock_manager.responses.append("""
[walbert_sql_execute_start]
CREATE TABLE IF NOT EXISTS test_table (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    value REAL
);
[walbert_sql_execute_end]

[walbert_console_response_start]
Created test table in database.
[walbert_console_response_end]

[walbert_summary_start]
Created test_table with id, name, and value columns
[walbert_summary_end]
""")

        # Response 3: Python execution with stdout and stderr
        self.mock_manager.responses.append("""
[walbert_python_execute_start]
import sys
print("Hello, stdout!")
print("Hello, stderr!", file=sys.stderr)
[walbert_python_execute_end]

[walbert_console_response_start]
Executed Python code to show stdout and stderr.
[walbert_console_response_end]

[walbert_summary_start]
Executed Python code to display stdout and stderr
[walbert_summary_end]
""")

        # Response 4: Error handling
        self.mock_manager.responses.append("""
[walbert_python_execute_start]
import nonexistent_module
print("This should fail")
[walbert_python_execute_end]

[walbert_console_response_start]
Attempted to execute Python code that should fail.
[walbert_console_response_end]

[walbert_summary_start]
Attempted Python execution with expected error
[walbert_summary_end]
""")

        # Response 5: Multiple SQL statements
        self.mock_manager.responses.append("""
[walbert_sql_execute_start]
INSERT INTO test_table (name, value) VALUES ('test1', 1.5);
[walbert_sql_execute_end]

[walbert_sql_execute_start]
INSERT INTO test_table (name, value) VALUES ('test2', 2.5);
[walbert_sql_execute_end]

[walbert_sql_execute_start]
SELECT * FROM test_table;
[walbert_sql_execute_end]

[walbert_console_response_start]
Inserted test data and queried the table.
[walbert_console_response_end]

[walbert_summary_start]
Inserted two rows into test_table and retrieved all data
[walbert_summary_end]
""")

        # Response 6: Context validation
        self.mock_manager.responses.append("""
[walbert_console_response_start]
Context validation complete. Ready for next command.
[walbert_console_response_end]

[walbert_summary_start]
Validated context and execution history
[walbert_summary_end]
""")

        # Response 7: Autonomous instruction
        self.mock_manager.responses.append("""
[walbert_autonomous_instruction_start]
Review the database schema and ensure all tables are properly indexed.
[walbert_autonomous_instruction_end]
""")

    # --- Helper Methods ---
    def _process_response(self, response_text):
        """Helper to parse and execute blocks from a response"""
        blocks = self.agent._parse_blocks(response_text)
        for block in blocks:
            self.agent._append_block(block["type"], block["content"])
        self.agent._execute_pending_blocks()

    def _get_block_content(self, block_type: str, index: int = 0) -> str:
        """Helper to get content of the nth block of a given type"""
        blocks = [b for b in self.agent.context_blocks if b["type"] == block_type]
        if index < len(blocks):
            return blocks[index]["content"]
        return ""

    def _count_blocks(self, block_type: str) -> int:
        """Helper to count blocks of a given type"""
        return len([b for b in self.agent.context_blocks if b["type"] == block_type])

    # --- Tests ---
    def test_block_parsing(self):
        """Test that blocks are parsed correctly"""
        self.agent.start_conversation()

        # Test parsing a response with multiple blocks
        response = self.mock_manager.responses[1]
        blocks = self.agent._parse_blocks(response)

        # Check that all blocks are parsed
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["type"], "sql_execute")
        self.assertIn("CREATE TABLE IF NOT EXISTS test_table", blocks[0]["content"])
        self.assertEqual(blocks[1]["type"], "console_response")
        self.assertEqual(blocks[2]["type"], "summary")

    def test_sql_execution_and_result(self):
        """Test that SQL blocks are executed and results are appended"""
        self.agent.start_conversation()

        # Process SQL execution response
        self._process_response(self.mock_manager.responses[1])

        # Check that SQL block was appended
        self.assertEqual(self._count_blocks("sql_execute"), 1)
        self.assertIn("CREATE TABLE IF NOT EXISTS test_table", self._get_block_content("sql_execute"))

        # Check that SQL result block was appended
        self.assertEqual(self._count_blocks("sql_result"), 1)

        # Check that console response was appended
        self.assertEqual(self._count_blocks("console_response"), 1)
        self.assertIn("Created test table in database", self._get_block_content("console_response"))

    @patch.object(WalbertAgent, '_execute_python_code', return_value="Python stdout:\nHello, stdout!\nPython stderr:\nHello, stderr!\nPython return code: 0\n")
    def test_python_execution_and_result(self, mock_execute_python):
        """Test that Python blocks are executed and results are appended"""
        self.agent.start_conversation()

        # Process Python execution response
        self._process_response(self.mock_manager.responses[2])

        # Check that Python block was appended
        self.assertEqual(self._count_blocks("python_execute"), 1)
        self.assertIn("print(\"Hello, stdout!\")", self._get_block_content("python_execute"))

        # Check that Python result block was appended
        self.assertEqual(self._count_blocks("python_result"), 1)
        python_result = self._get_block_content("python_result")
        self.assertIn("Hello, stdout!", python_result)
        self.assertIn("Hello, stderr!", python_result)

    @patch.object(WalbertAgent, '_execute_python_code', return_value="Python stderr:\nModuleNotFoundError: No module named 'nonexistent_module'\nPython return code: 1\n")
    def test_error_handling(self, mock_execute_python):
        """Test that errors in Python execution are captured in result blocks"""
        self.agent.start_conversation()

        # Process error response
        self._process_response(self.mock_manager.responses[3])

        # Check that Python block was appended
        self.assertEqual(self._count_blocks("python_execute"), 1)

        # Check that Python result block contains error
        self.assertEqual(self._count_blocks("python_result"), 1)
        python_result = self._get_block_content("python_result")
        self.assertIn("nonexistent_module", python_result)

    def test_multiple_sql_blocks(self):
        """Test handling of multiple SQL execution blocks"""
        self.agent.start_conversation()

        # Process response with multiple SQL blocks
        self._process_response(self.mock_manager.responses[4])

        # Check that all SQL blocks were appended
        self.assertEqual(self._count_blocks("sql_execute"), 3)

        # Check that all SQL result blocks were appended
        self.assertEqual(self._count_blocks("sql_result"), 3)

        # Check that console response was appended
        self.assertEqual(self._count_blocks("console_response"), 1)

    def test_context_blocks_persistence(self):
        """Test that context_blocks persists all blocks in order"""
        self.agent.start_conversation()

        # Process multiple responses
        self._process_response(self.mock_manager.responses[1])  # SQL
        self._process_response(self.mock_manager.responses[2])  # Python
        self._process_response(self.mock_manager.responses[3])  # Error

        # Check that all blocks are present in context_blocks
        self.assertEqual(self._count_blocks("system_prompt"), 1)
        self.assertEqual(self._count_blocks("sql_execute"), 1)
        self.assertEqual(self._count_blocks("sql_result"), 1)
        self.assertEqual(self._count_blocks("python_execute"), 2)  # One from Python, one from error
        self.assertEqual(self._count_blocks("python_result"), 2)  # One from Python, one from error
        self.assertEqual(self._count_blocks("console_response"), 3)  # One from SQL, Python, and Error

    def test_context_as_text(self):
        """Test that _get_context_as_text returns all blocks in order"""
        self.agent.start_conversation()

        # Process a response
        self._process_response(self.mock_manager.responses[1])

        # Get context as text
        context_text = self.agent._get_context_as_text()

        # Check that all blocks are included in the text
        self.assertIn("[walbert_system_prompt_start]", context_text)
        self.assertIn("[walbert_sql_execute_start]", context_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS test_table", context_text)
        self.assertIn("[walbert_sql_result_start]", context_text)
        self.assertIn("[walbert_console_response_start]", context_text)

    def test_autonomous_instruction(self):
        """Test that autonomous instructions are parsed and appended"""
        self.agent.start_conversation()

        # Process autonomous instruction response
        self._process_response(self.mock_manager.responses[6])

        # Check that autonomous instruction block was appended
        self.assertEqual(self._count_blocks("autonomous_instruction"), 1)
        self.assertIn("Review the database schema", self._get_block_content("autonomous_instruction"))

    def test_user_input_block(self):
        """Test that user input is appended as a block"""
        self.agent.start_conversation()

        # Simulate user input
        user_input = "What is the current database schema?"
        self.agent._append_block("user_input", user_input)

        # Check that user input block was appended
        self.assertEqual(self._count_blocks("user_input"), 1)
        self.assertEqual(self._get_block_content("user_input"), user_input)

    @patch.object(WalbertAgent, '_execute_python_code', return_value="Python stdout:\nTable created\nPython return code: 0\n")
    def test_block_execution_order(self, mock_execute_python):
        """Test that blocks are executed in the order they are appended"""
        self.agent.start_conversation()

        # Append blocks in a specific order
        self.agent._append_block("user_input", "Create a test table")
        self.agent._append_block("sql_execute", "CREATE TABLE test_order (id INTEGER);")
        self.agent._append_block("python_execute", "print('Table created')")

        # Execute pending blocks
        self.agent._execute_pending_blocks()

        # Check that blocks were executed in order
        self.assertEqual(self._count_blocks("sql_result"), 1)
        self.assertEqual(self._count_blocks("python_result"), 1)

        # Check that SQL was executed before Python
        sql_result_time = next(b["timestamp"] for b in self.agent.context_blocks if b["type"] == "sql_result")
        python_result_time = next(b["timestamp"] for b in self.agent.context_blocks if b["type"] == "python_result")
        self.assertLess(sql_result_time, python_result_time)

    def test_schema_updates_in_context(self):
        """Test that schema updates are reflected in context_blocks"""
        self.agent.start_conversation()

        # Process SQL to create a table
        self._process_response(self.mock_manager.responses[1])

        # Check that the SQL execution and result are in context_blocks
        self.assertEqual(self._count_blocks("sql_execute"), 1)
        self.assertEqual(self._count_blocks("sql_result"), 1)

    def test_internet_access_context(self):
        """Test that internet access status is included in system prompt"""
        self.agent.start_conversation()

        # Check system prompt block includes internet access status
        system_prompt = self._get_block_content("system_prompt")
        self.assertIn("Internet access for Python execution is currently DISABLED", system_prompt)

        # Enable internet access and check again
        self.agent.internet_access = True
        self.agent._append_block("system_prompt", self.agent._build_system_prompt())
        system_prompt = self._get_block_content("system_prompt", 1)
        self.assertIn("Internet access for Python execution is currently ENABLED", system_prompt)

    def test_conversation_file_logging(self):
        """Test that blocks are logged to conversation files"""
        self.agent.start_conversation()

        # Call _generate_response_block to trigger model execution and logging
        self.agent._generate_response_block("Test input")

        # Check that session_dir exists
        self.assertIsNotNone(self.agent.session_dir)
        self.assertTrue(os.path.exists(self.agent.session_dir))

        # Check that files were created in the session directory
        files = os.listdir(self.agent.session_dir)
        self.assertTrue(any("conversation" in f for f in files))


if __name__ == "__main__":
    unittest.main()