#!/usr/bin/env python3
"""
End-to-end test for WalbertAgent with mocked LLM
Validates context, conversation history, Python/SQL execution, and error handling
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

class MockModelManager:
    """Mock ModelManager for testing"""
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
    """End-to-end test for WalbertAgent"""

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

        # Patch ModelManager creation
        self.patcher = patch('walbert.agent.ModelManager', return_value=self.mock_manager)
        self.mock_model_manager = self.patcher.start()

        # Create agent
        self.agent = WalbertAgent(self.config, self.mock_manager)
        self.agent.db.connect()

        # Set up test responses
        self._setup_test_responses()

    def tearDown(self):
        """Clean up test environment"""
        self.agent.shutdown()
        self.patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _setup_test_responses(self):
        """Set up test responses for the mock model"""
        # Response 1: Simple console response
        self.mock_manager.responses.append("""
[walbert_console_response]
Hello! How can I help you today?
[/walbert_console_response]

[walbert_summary]
Provided greeting to user
[/walbert_summary]
""")

        # Response 2: SQL execution
        self.mock_manager.responses.append("""
[walbert_sql_execute]
CREATE TABLE IF NOT EXISTS test_table (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    value REAL
);
[/walbert_sql_execute]

[walbert_console_response]
Created test table in database.
[/walbert_console_response]

[walbert_summary]
Created test_table with id, name, and value columns
[/walbert_summary]
""")

        # Response 3: Python execution with stdout and stderr
        self.mock_manager.responses.append("""
[walbert_python_execute]
import sys
print("Hello, stdout!")
print("Hello, stderr!", file=sys.stderr)
[/walbert_python_execute]

[walbert_console_response]
Executed Python code to show stdout and stderr.
[/walbert_console_response]

[walbert_summary]
Executed Python code to display stdout and stderr
[/walbert_summary]
""")

        # Response 4: Error handling
        self.mock_manager.responses.append("""
[walbert_python_execute]
import nonexistent_module
print("This should fail")
[/walbert_python_execute]

[walbert_console_response]
Attempted to execute Python code that should fail.
[/walbert_console_response]

[walbert_summary]
Attempted Python execution with expected error
[/walbert_summary]
""")

        # Response 5: Multiple SQL statements
        self.mock_manager.responses.append("""
[walbert_sql_execute]
INSERT INTO test_table (name, value) VALUES ('test1', 1.5);
[/walbert_sql_execute]

[walbert_sql_execute]
INSERT INTO test_table (name, value) VALUES ('test2', 2.5);
[/walbert_sql_execute]

[walbert_sql_execute]
SELECT * FROM test_table;
[/walbert_sql_execute]

[walbert_console_response]
Inserted test data and queried the table.
[/walbert_console_response]

[walbert_summary]
Inserted two rows into test_table and retrieved all data
[/walbert_summary]
""")

        # Response 6: Context validation
        self.mock_manager.responses.append("""
[walbert_console_response]
Context validation complete. Ready for next command.
[/walbert_console_response]

[walbert_summary]
Validated context and execution history
[/walbert_summary]
""")

    def test_context_validation(self):
        """Test that context includes execution results and history"""
        self.agent.start_conversation()

        # Process SQL execution response
        response = self.mock_manager.responses[1]
        parsed = self.agent.process_response(response)

        # Check that SQL was executed
        self.assertIn("sql_execute", parsed)
        self.assertEqual(len(parsed["sql_execute"]), 1)

        # Reset context to validate proper content
        self.agent._reset_conversation_context()

        # Check that context includes the execution results
        self.assertIn("Last Execution Results", self.agent.conversation_context)
        self.assertIn("SQL Execution", self.agent.conversation_context)
        self.assertIn("test_table", self.agent.conversation_context)

        # Process Python execution response
        response = self.mock_manager.responses[2]
        parsed = self.agent.process_response(response)

        # Check that Python was executed
        self.assertIn("python_execute", parsed)
        self.assertEqual(len(parsed["python_execute"]), 1)

        # Reset context to validate proper content
        self.agent._reset_conversation_context()

        # Check that context includes Python execution results
        self.assertIn("Last Execution Results", self.agent.conversation_context)
        self.assertIn("Python Execution", self.agent.conversation_context)
        self.assertIn("Hello, stdout!", self.agent.conversation_context)
        self.assertIn("Hello, stderr!", self.agent.conversation_context)

        # Process error response
        response = self.mock_manager.responses[3]
        parsed = self.agent.process_response(response)

        # Check that error was captured
        self.assertIn("python_execute", parsed)

        # Reset context to validate error handling
        self.agent._reset_conversation_context()

        # Check that context includes error information
        self.assertIn("Last Execution Results", self.agent.conversation_context)
        self.assertIn("Python Execution", self.agent.conversation_context)
        self.assertIn("nonexistent_module", self.agent.conversation_context)

    def test_python_execution_capture(self):
        """Test that Python stdout/stderr are captured and included in context"""
        self.agent.start_conversation()

        # Process Python execution response
        response = self.mock_manager.responses[2]
        parsed = self.agent.process_response(response)

        # Check that Python was executed
        self.assertIn("python_execute", parsed)

        # Check that stdout and stderr are captured in last_execution_results
        self.assertIn("Hello, stdout!", self.agent.last_execution_results["python"])
        self.assertIn("Hello, stderr!", self.agent.last_execution_results["python"])

        # Reset context and check that results are included
        self.agent._reset_conversation_context()
        self.assertIn("Hello, stdout!", self.agent.conversation_context)
        self.assertIn("Hello, stderr!", self.agent.conversation_context)

    def test_sql_execution_capture(self):
        """Test that SQL execution results are captured and included in context"""
        self.agent.start_conversation()

        # Process SQL execution response
        response = self.mock_manager.responses[1]
        parsed = self.agent.process_response(response)

        # Check that SQL was executed
        self.assertIn("sql_execute", parsed)

        # Check that SQL result is captured
        self.assertIn("test_table", self.agent.last_execution_results["sql"])

        # Reset context and check that results are included
        self.agent._reset_conversation_context()
        self.assertIn("test_table", self.agent.conversation_context)

    def test_error_capture(self):
        """Test that Python errors are captured and included in context"""
        self.agent.start_conversation()

        # Process error response
        response = self.mock_manager.responses[3]
        parsed = self.agent.process_response(response)

        # Check that Python was executed
        self.assertIn("python_execute", parsed)

        # Check that error is captured
        self.assertIn("nonexistent_module", self.agent.last_execution_results["python"])

        # Reset context and check that error is included
        self.agent._reset_conversation_context()
        self.assertIn("nonexistent_module", self.agent.conversation_context)

    def test_history_preservation(self):
        """Test that conversation history is properly preserved"""
        self.agent.start_conversation()

        # Add some history entries
        self.agent.conversation_history.append({
            "type": "question",
            "content": "First question",
            "timestamp": time.time()
        })
        self.agent.conversation_history.append({
            "type": "summary",
            "content": "First answer",
            "timestamp": time.time()
        })
        self.agent.conversation_history.append({
            "type": "question",
            "content": "Second question",
            "timestamp": time.time()
        })
        self.agent.conversation_history.append({
            "type": "summary",
            "content": "Second answer",
            "timestamp": time.time()
        })

        # Reset context to include history
        self.agent._reset_conversation_context()

        # Check that context includes recent history
        self.assertIn("Recent Conversation History", self.agent.conversation_context)
        self.assertIn("First question", self.agent.conversation_context)
        self.assertIn("Second question", self.agent.conversation_context)
        self.assertIn("First answer", self.agent.conversation_context)
        self.assertIn("Second answer", self.agent.conversation_context)

    def test_schema_updates(self):
        """Test that schema updates are reflected in context"""
        self.agent.start_conversation()

        # Get initial schema
        initial_schema = self.agent.db.get_schema()
        self.assertIn("Table: items", initial_schema)

        # Process SQL execution that creates a table
        response = self.mock_manager.responses[1]
        parsed = self.agent.process_response(response)

        # Get updated schema
        updated_schema = self.agent.db.get_schema()
        self.assertIn("Table: test_table", updated_schema)

        # Reset context and check schema is included
        self.agent._reset_conversation_context()
        self.assertIn("Current Database Schema", self.agent.conversation_context)
        self.assertIn("Table: test_table", self.agent.conversation_context)

        # Process multiple SQL statements
        response = self.mock_manager.responses[4]
        parsed = self.agent.process_response(response)

        # Verify data was inserted
        self.assertIn("test1", self.agent.last_execution_results["sql"])
        self.assertIn("test2", self.agent.last_execution_results["sql"])

    def test_internet_access_context(self):
        """Test that internet access status is included in context"""
        self.agent.start_conversation()

        # Test with internet access disabled
        self.agent.internet_access = False
        self.agent._reset_conversation_context()
        self.assertIn("Internet access for Python execution is currently DISABLED",
                     self.agent.conversation_context)

        # Test with internet access enabled
        self.agent.internet_access = True
        self.agent._reset_conversation_context()
        self.assertIn("Internet access for Python execution is currently ENABLED",
                     self.agent.conversation_context)

    def test_multiple_block_execution(self):
        """Test handling of multiple execution blocks"""
        self.agent.start_conversation()

        # Process response that creates the table
        response1 = self.mock_manager.responses[1]
        self.agent.process_response(response1)

        # Process response with multiple SQL statements
        response = self.mock_manager.responses[4]
        parsed = self.agent.process_response(response)

        # Check that multiple SQL statements were parsed
        self.assertIn("sql_execute", parsed)
        self.assertEqual(len(parsed["sql_execute"]), 3)

        # Process response with console response and summary
        response = self.mock_manager.responses[5]
        parsed = self.agent.process_response(response)

        # Check that console response and summary were parsed
        self.assertIn("console_response", parsed)
        self.assertIn("summary", parsed)

if __name__ == "__main__":
    unittest.main()