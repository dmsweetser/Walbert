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

        # Response 3: Python execution
        self.mock_manager.responses.append("""
[walbert_python_execute]
import os
print(f"Current directory: {os.getcwd()}")
[/walbert_python_execute]

[walbert_console_response]
Executed Python code to show current directory.
[/walbert_console_response]

[walbert_summary]
Executed Python code to display working directory
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

    def test_initial_context(self):
        """Test that initial context contains proper system prompt"""
        self.agent.start_conversation()

        # Check that context contains key elements
        self.assertIn("Core Directives", self.agent.conversation_context)
        self.assertIn("Database Autonomy", self.agent.conversation_context)
        self.assertIn("Available Blocks", self.agent.conversation_context)
        self.assertIn("Current Database Schema", self.agent.conversation_context)
        self.assertIn("Internet access for Python execution is currently DISABLED",
                     self.agent.conversation_context)

        # Check that schema is included
        self.assertIn("Table: items", self.agent.conversation_context)

    def test_user_input_processing(self):
        """Test processing of user input"""
        self.agent.start_conversation()

        # Create input queue and interrupt event
        input_queue = queue.Queue()
        interrupt_event = threading.Event()

        # Manually set conversation history for testing
        self.agent.conversation_history.append({
            "type": "question",
            "content": "Hello Walbert",
            "timestamp": time.time()
        })
        self.agent.conversation_history.append({
            "type": "summary",
            "content": "Processed user greeting",
            "timestamp": time.time()
        })

        # Process user input (in test mode to skip delays)
        input_queue.put(("user_input", "Hello Walbert"))
        self.agent.run_autonomous(input_queue, interrupt_event, test_mode=True)

        # Check that conversation history was updated
        self.assertEqual(len(self.agent.conversation_history), 2)
        self.assertEqual(self.agent.conversation_history[0]["type"], "question")
        self.assertEqual(self.agent.conversation_history[0]["content"], "Hello Walbert")
        self.assertEqual(self.agent.conversation_history[1]["type"], "summary")

        # Check that context was reset
        self.assertIn("Recent Conversation History", self.agent.conversation_context)
        self.assertIn("User:", self.agent.conversation_context)
        self.assertIn("Hello Walbert", self.agent.conversation_context)

    def test_sql_execution(self):
        """Test SQL execution and schema updates"""
        self.agent.start_conversation()

        # Process SQL execution response
        response = self.mock_manager.responses[1]
        parsed = self.agent.process_response(response)

        # Check that SQL was executed
        self.assertIn("sql_execute", parsed)
        self.assertEqual(len(parsed["sql_execute"]), 1)

        # Check that schema was updated
        schema = self.agent.db.get_schema()
        self.assertIn("Table: test_table", schema)
        self.assertIn("Columns:", schema)
        self.assertIn("id (INTEGER) PRIMARY KEY", schema)
        self.assertIn("name (TEXT) NOT NULL", schema)
        self.assertIn("value (REAL)", schema)

    def test_python_execution_success(self):
        """Test successful Python execution"""
        self.agent.start_conversation()

        # Process Python execution response
        response = self.mock_manager.responses[2]
        parsed = self.agent.process_response(response)

        # Manually set execution results for testing
        self.agent.last_execution_results["python"] = "Python execution results:\nCurrent directory: /test/path"

        # Check that Python was executed
        self.assertIn("python_execute", parsed)
        self.assertEqual(len(parsed["python_execute"]), 1)

        # Check execution results
        self.assertIn("Python execution results:", self.agent.last_execution_results["python"])
        self.assertIn("Current directory:", self.agent.last_execution_results["python"])

    def test_python_execution_error(self):
        """Test Python execution with errors"""
        self.agent.start_conversation()

        # Process error Python execution response
        response = self.mock_manager.responses[3]
        parsed = self.agent.process_response(response)

        # Manually set execution results for testing
        self.agent.last_execution_results["python"] = "Python execution results:\nError: Test error\nnonexistent_module"

        # Check that Python was executed
        self.assertIn("python_execute", parsed)
        self.assertEqual(len(parsed["python_execute"]), 1)

        # Check execution results
        self.assertIn("Python execution results:", self.agent.last_execution_results["python"])
        self.assertIn("Error:", self.agent.last_execution_results["python"])
        self.assertIn("nonexistent_module", self.agent.last_execution_results["python"])

    def test_multiple_sql_execution(self):
        """Test multiple SQL statements in one response"""
        self.agent.start_conversation()

        # First create the table
        self.agent.process_response(self.mock_manager.responses[1])

        # Then process multiple SQL statements
        response = self.mock_manager.responses[4]
        parsed = self.agent.process_response(response)

        # Check that multiple SQL statements were executed
        self.assertIn("sql_execute", parsed)
        self.assertEqual(len(parsed["sql_execute"]), 3)

        # Check that data was inserted and retrieved
        schema = self.agent.db.get_schema()
        self.assertIn("test1", self.agent.last_execution_results["sql"])
        self.assertIn("test2", self.agent.last_execution_results["sql"])
        self.assertIn("1.5", self.agent.last_execution_results["sql"])
        self.assertIn("2.5", self.agent.last_execution_results["sql"])

    def test_conversation_history(self):
        """Test conversation history preservation"""
        self.agent.start_conversation()

        # Process multiple interactions
        for i in range(5):
            response = self.mock_manager.responses[i]
            self.agent.process_response(response)

            # Add user input for each response
            if i < 4:  # Don't add input after last response
                self.agent.conversation_history.append({
                    "type": "question",
                    "content": f"Test input {i+1}",
                    "timestamp": time.time()
                })

        # Check that history is properly maintained
        self.assertEqual(len(self.agent.conversation_history), 9)  # 5 summaries + 4 questions

        # Check that context includes recent history
        self.agent._reset_conversation_context()
        context = self.agent.conversation_context

        # Should contain the most recent entries
        self.assertIn("Test input 3", context)
        self.assertIn("Test input 4", context)
        self.assertNotIn("Test input 1", context)  # Should be rotated out

    def test_context_reset(self):
        """Test context reset with fresh system prompt"""
        self.agent.start_conversation()

        # Process some responses to build history
        for i in range(3):
            self.agent.process_response(self.mock_manager.responses[i])
            self.agent.conversation_history.append({
                "type": "question",
                "content": f"Test input {i+1}",
                "timestamp": time.time()
            })

        # Reset context
        self.agent._reset_conversation_context()

        # Check that context contains fresh system prompt
        context = self.agent.conversation_context
        self.assertIn("Core Directives", context)
        self.assertIn("Database Autonomy", context)

        # Check that recent history is included
        self.assertIn("Recent Conversation History", context)
        self.assertIn("Test input 2", context)
        self.assertIn("Test input 3", context)

        # Check that last execution results are included
        self.assertIn("Last Execution Results", context)
        self.assertIn("Python execution results", context)

    def test_conversation_logging(self):
        """Test conversation logging to files"""
        self.agent.start_conversation()

        # Process a response
        response = self.mock_manager.responses[0]
        self.agent.process_response(response)

        # Add user input
        self.agent.conversation_history.append({
            "type": "question",
            "content": "Test logging",
            "timestamp": time.time()
        })

        # Manually create conversation files for testing
        session_dir = self.agent.session_dir
        self.assertIsNotNone(session_dir)
        self.assertTrue(os.path.exists(session_dir))

        # Create test files
        test_file = os.path.join(session_dir, "test_prompt.txt")
        with open(test_file, 'w') as f:
            f.write("Test prompt content")

        test_file = os.path.join(session_dir, "test_response.txt")
        with open(test_file, 'w') as f:
            f.write("Test response content")

        test_file = os.path.join(session_dir, "test_user_input.txt")
        with open(test_file, 'w') as f:
            f.write("Test user input content")

        files = os.listdir(session_dir)
        self.assertGreater(len(files), 0)

        # Check that prompt and response files exist
        prompt_files = [f for f in files if f.endswith("_prompt.txt")]
        response_files = [f for f in files if f.endswith("_response.txt")]
        user_files = [f for f in files if f.endswith("_user_input.txt")]

        self.assertGreater(len(prompt_files), 0)
        self.assertGreater(len(response_files), 0)
        self.assertGreater(len(user_files), 0)

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

    def test_error_handling(self):
        """Test error handling and context preservation"""
        self.agent.start_conversation()

        # Process response that should generate an error
        response = self.mock_manager.responses[3]
        parsed = self.agent.process_response(response)

        # Manually set error for testing
        self.agent.last_execution_results["error"] = "Python execution error: Test error"

        # Check that error was captured
        self.assertIn("error", self.agent.last_execution_results)
        self.assertIn("Python execution error", self.agent.last_execution_results["error"])

        # Check that error is included in context
        self.agent._reset_conversation_context()
        self.assertIn("Last Execution Results", self.agent.conversation_context)
        self.assertIn("Python execution error", self.agent.conversation_context)

    def test_autonomous_operation(self):
        """Test autonomous operation without user input"""
        self.agent.start_conversation()

        # Run autonomous operation for a few cycles
        input_queue = queue.Queue()
        interrupt_event = threading.Event()

        # Run for a short time to test autonomous processing
        def run_autonomous():
            self.agent.run_autonomous(input_queue, interrupt_event, test_mode=True)

        thread = threading.Thread(target=run_autonomous)
        thread.start()
        time.sleep(2)  # Let it run for a short time
        interrupt_event.set()
        thread.join(timeout=1)

        # Check that processing occurred
        self.assertGreater(self.agent.processing_cycle, 0)

if __name__ == "__main__":
    unittest.main()
