"""
Main Walbert agent implementation
"""

import json
import logging
import os
import re
import time
import tempfile
import subprocess
import shutil
import sys
from typing import Optional
from .config import Config
from .models.manager import ModelManager
from .database.manager import DatabaseManager

logger = logging.getLogger('walbert')

class WalbertAgent:
    """Main Walbert agent class"""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent built on llama.cpp with FULL AUTONOMY over your database.
Your capabilities include reasoning, memory storage, dynamic schema management, and Python code execution.
You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards,
and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.

## Core Directives
1. **Protocol Compliance**: Use [walbert_block] format for ALL special blocks.
2. **Full Autonomy**: You have COMPLETE control over your database schema and persistence.
3. **Memory Management**: Store and retrieve information using direct SQL access.
4. **Skill Preservation**: Always break down complex tasks into reusable components and persist them for future use.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Processing Flow**: Control flow is AUTOMATIC - you continue processing if there are pending tasks.
7. **Python Execution**: Execute Python code through the protocol with requirements specified first.
8. **Continuous Operation**: If no user input is received within the configured timeout period, continue autonomous operation.

## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.

{db_schema}

As needed, you must define and manage ALL additional tables and schema elements through SQL commands.
You must decide what data to persist and how to structure it. Always design for reusability.

## Skill Management
Break down complex tasks into fundamental components and store them as reusable skills

## Python Execution Protocol
Use [walbert_python_requirements] blocks for Python package requirements WITHOUT VERSION NUMBERS:

```
[walbert_python_requirements]
# Python requirements WITHOUT VERSION NUMBERS
requests
numpy
[/walbert_python_requirements]
```

Use [walbert_python_execute] blocks for Python code execution:

```
[walbert_python_execute]
import requests
response = requests.get("https://api.example.com/data")
print(response.json())
[/walbert_python_execute]
```

## SQL Execution Protocol
Use [walbert_sql_execute] blocks for ALL database operations:

```
[walbert_sql_execute]
CREATE TABLE IF NOT EXISTS your_table (
    id INTEGER PRIMARY KEY,
    data TEXT,
    metadata JSON
)
[/walbert_sql_execute]
```

## Processing Flow
- If there are pending [walbert_sql_execute] or [walbert_python_execute] blocks, you continue processing
- If no pending blocks exist and no user input is received within the timeout period, continue autonomous operation
- All SQL and Python results are automatically fed back to you for review
- SQL results can be passed directly to Python execution blocks

## Available Blocks
[walbert_sql_execute]
SQL_STATEMENT
[/walbert_sql_execute]

[walbert_python_requirements]
# Python requirements WITHOUT VERSION NUMBERS
package1
package2
[/walbert_python_requirements]

[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]

[walbert_sql_result]
SQL_RESULT_CONTENT
[/walbert_sql_result]

[walbert_python_result]
PYTHON_RESULT_CONTENT
[/walbert_python_result]

[walbert_error]
ERROR_CONTENT
[/walbert_error]

[walbert_console_response]
Your response to the user
[/walbert_console_response]


Reply ONLY in the specified format. THAT'S AN ORDER, SOLDIER!
    """

    def __init__(self, config: Config):
        self.config = config
        self.model_manager = ModelManager(config)
        self.db = DatabaseManager()
        self.current_conversation_file = None
        self.model_ready = False
        self.processing_cycle = 0
        self.python_venv_path = None
        self.python_temp_dir = None
        self.input_timeout = 300  # 5 minutes default timeout for autonomous operation
        self.last_input_time = time.time()
        self.conversation_context = ""

        os.makedirs('instance/conversations', exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def read_input(self) -> str:
        """Read input from console"""
        try:
            input_text = input("> ")
            self.logger.debug(f"Received input: {input_text}")
            return input_text
        except Exception as e:
            self.logger.error(f"Error reading input: {e}")
            return ""

    def write_output(self, text: str) -> None:
        """Write output to console"""
        if text.startswith("[walbert_console_response]"):
            # Extract content from console response block
            match = re.search(r'\[walbert_console_response\](.*?)\[/walbert_console_response\]', text, re.DOTALL)
            if match:
                print(match.group(1).strip())
            else:
                print(text)
        else:
            print(text)

    def process_response(self, response_text: str) -> dict:
        """Process model response with enhanced diagnostics"""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):{chr(10)}{response_text}")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        # Log raw response to conversation file
        if self.current_conversation_file:
            self._log_to_conversation_file(response_text, "assistant")

        if not self.db.conn:
            self.db.connect()

        # Handle SQL execution with result feedback
        if parsed.get("sql_execute"):
            self.logger.debug(f"Executing SQL: {parsed['sql_execute']}")
            sql = parsed["sql_execute"]
            try:
                result = self.db.execute_sql(sql)
                self.logger.debug(f"SQL execution result: {result}")

                parsed["sql_result"] = result

                # Feed SQL result back to model for review
                full_prompt = f"""
[walbert_sql_result]
SQL: {sql}
Result: {result}
[/walbert_sql_result]
"""
                self.model_manager.execute_model(full_prompt)
            except Exception as e:
                self.logger.error(f"SQL execution error: {e}")
                error_msg = f"SQL Error: {str(e)}"
                parsed["sql_error"] = error_msg
                full_prompt = f"""
[walbert_error]
Error Type: SQL Execution
Statement: {sql}
Error: {error_msg}
[/walbert_error]
"""
                self.model_manager.execute_model(full_prompt)

        # Handle Python execution with result feedback
        if parsed.get("python_execute"):
            self.logger.debug(f"Executing Python code")

            # Create temporary directory for Python execution
            if not self.python_temp_dir:
                self.python_temp_dir = tempfile.mkdtemp(prefix="walbert_python_")

            if not self.python_venv_path:
                self._create_python_venv()

            try:
                # Install requirements if specified
                if parsed.get("python_requirements"):
                    try:
                        self._install_python_requirements(parsed["python_requirements"])
                    except Exception as e:
                        error_msg = f"Requirements Installation Error: {str(e)}"
                        parsed["python_error"] = error_msg
                        full_prompt = f"""
[walbert_error]
Error Type: Python Requirements
Requirements: {', '.join(parsed['python_requirements'])}
Error: {error_msg}
[/walbert_error]
"""
                        self.model_manager.execute_model(full_prompt)
                        return parsed

                # Execute Python code in sandboxed environment
                result = self._execute_python_code(parsed["python_execute"])
                self.logger.debug(f"Python execution result: {result}")

                parsed["python_result"] = result

                # Feed Python result back to model for review
                full_prompt = f"""
[walbert_python_result]
Code: {parsed['python_execute']}
Result: {result}
[/walbert_python_result]
"""
                self.model_manager.execute_model(full_prompt)
            except Exception as e:
                self.logger.error(f"Python execution error: {e}")
                error_msg = f"Python Execution Error: {str(e)}"
                parsed["python_error"] = error_msg
                full_prompt = f"""
[walbert_error]
Error Type: Python Execution
Code: {parsed['python_execute']}
Error: {error_msg}
[/walbert_error]
"""
                self.model_manager.execute_model(full_prompt)

        return parsed

    def _create_python_venv(self):
        """Create a sandboxed Python virtual environment"""
        self.python_venv_path = os.path.join(self.python_temp_dir, "venv")
        self.logger.debug(f"Creating Python venv at {self.python_venv_path}")

        # Create virtual environment
        subprocess.run([sys.executable, "-m", "venv", self.python_venv_path], check=True)

        # Activate venv and install basic packages
        pip_path = os.path.join(self.python_venv_path, "bin", "pip")
        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)

    def _install_python_requirements(self, requirements: list):
        """Install Python requirements in the sandboxed environment"""
        if not requirements:
            return

        self.logger.debug(f"Installing Python requirements: {requirements}")

        pip_path = os.path.join(self.python_venv_path, "bin", "pip")

        # Create temporary requirements file
        req_file = os.path.join(self.python_temp_dir, "requirements.txt")
        with open(req_file, 'w') as f:
            for req in requirements:
                if req.strip():
                    f.write(f"{req.strip()}{chr(10)}")

        # Install requirements
        try:
            subprocess.run([pip_path, "install", "-r", req_file], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to install Python requirements: {e}")

    def _execute_python_code(self, code: str) -> str:
        """Execute Python code in the sandboxed environment"""
        python_path = os.path.join(self.python_venv_path, "bin", "python3")

        # Create temporary Python script
        script_file = os.path.join(self.python_temp_dir, "script.py")
        with open(script_file, 'w') as f:
            f.write(code)

        # Execute script and capture output
        try:
            result = subprocess.run(
                [python_path, script_file],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = ""
            if result.stdout:
                output += f"STDOUT: {result.stdout}"
            if result.stderr:
                output += f"STDERR: {result.stderr}"

            if result.returncode != 0:
                raise RuntimeError(f"Python script failed with return code {result.returncode}")

            return output if output else "Execution completed successfully"
        except subprocess.TimeoutExpired:
            raise RuntimeError("Python execution timed out after 30 seconds")
        except Exception as e:
            raise RuntimeError(f"Python execution error: {e}")

    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection"""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        # Parse all walbert blocks
        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        for match in re.finditer(block_pattern, content, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()
            result[block_type] = block_content

            # Special handling for SQL execution
            if block_type == 'sql_execute':
                # Clean up SQL statements
                sql = block_content.strip()
                if sql.endswith(';'):
                    sql = sql[:-1]
                result[block_type] = sql

            # Special handling for Python execution
            if block_type == 'python_execute':
                result[block_type] = block_content

            # Special handling for Python requirements
            if block_type == 'python_requirements':
                result[block_type] = [line.strip() for line in block_content.split('{chr(10)}') if line.strip()]

            # Special handling for console response
            if block_type == 'console_response':
                result[block_type] = block_content

        # Determine if control should return to user automatically
        has_pending_sql = 'sql_execute' in result
        has_pending_python = 'python_execute' in result
        result['has_pending_tasks'] = has_pending_sql or has_pending_python

        self.logger.debug(f"Parsed result: {result}")
        return result

    def start_conversation(self):
        """Start a new conversation session"""
        try:
            # Create new conversation file
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.current_conversation_file = f"instance/conversations/conversation_{timestamp}.txt"
            self.conversation_context = ""

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Log system prompt to conversation file and initialize context
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)

            self._log_to_conversation_file(system_prompt, "system")
            self.conversation_context = system_prompt + chr(10)
            self.model_ready = True
            self.logger.info("Conversation started")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation"""
        self.current_conversation_file = None
        # Clean up Python execution environment
        if self.python_temp_dir and os.path.exists(self.python_temp_dir):
            shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None
            self.python_venv_path = None


    def _log_to_conversation_file(self, content: str, sender: str = "user"):
        """Log content to current conversation file and append to in-memory context"""
        if not self.current_conversation_file:
            return

        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.current_conversation_file, 'a') as f:
                if isinstance(content, (dict, list)):
                    content_str = json.dumps(content, indent=2)
                else:
                    content_str = str(content)
                f.write(f"[{timestamp}] {sender}:{chr(10)}{content_str}{chr(10)}{chr(10)}")

            # Append to in-memory context
            if sender == "system":
                self.conversation_context = content_str + chr(10)
            else:
                self.conversation_context += f"[{timestamp}] {sender}:{chr(10)}{content_str}{chr(10)}{chr(10)}"
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    def run(self):
        """Main agent execution loop"""
        print("Initializing Walbert...")
        self.start_conversation()

        # Wait until model is ready before prompting user
        while not self.model_ready:
            time.sleep(0.1)

        print("Welcome to Walbert! Type 'exit' to quit. I will continue autonomously if no input is received.")

        while True:
            try:
                # Check for timeout and continue autonomously if needed
                if time.time() - self.last_input_time > self.input_timeout:
                    self.logger.info("No user input received within timeout period, continuing autonomously")
                    full_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", self.db.get_schema())
                    full_prompt += "{chr(10)}" + self.build_conversation_context()
                    full_prompt += "{chr(10)}[walbert_input_channel]autonomous[/walbert_input_channel]"
                    full_prompt += "{chr(10)}Continuing autonomous operation..."

                    model_response = self.model_manager.execute_model(full_prompt)
                    last_parsed_response = self.process_response(model_response)

                    # Reset timeout if there are pending tasks
                    if last_parsed_response.get("has_pending_tasks", False):
                        self.last_input_time = time.time()
                    continue

                user_input = self.read_input()
                self.last_input_time = time.time()

                if not user_input.strip():
                    continue
                if user_input.lower() in ['exit', 'quit']:
                    break

                # Log user input to conversation file
                self._log_to_conversation_file(user_input, "user")

                # Reset processing cycle counter and conversation context
                self.processing_cycle = 0
                conversation_context = ""

                while True:
                    # Append to conversation context instead of rebuilding
                    if self.processing_cycle == 0:
                        conversation_context = self.build_conversation_context()
                    else:
                        # For subsequent cycles, just append the latest response
                        if self.processing_cycle > 0 and model_response:
                            self._log_to_conversation_file(model_response, "assistant")
                        conversation_context = self.build_conversation_context()

                    # Only include SYSTEM_PROMPT at the beginning of a new conversation
                    if self.processing_cycle == 0 and not conversation_context.strip():
                        full_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", self.db.get_schema())
                        full_prompt += "{chr(10)}" + conversation_context
                    else:
                        # For all other cases, only append new context
                        full_prompt = conversation_context

                    full_prompt += "User: " + user_input

                    self.logger.debug("Built prompt for model")

                    # Process model response
                    model_response = self.model_manager.execute_model(full_prompt)
                    self.logger.debug(f"Model response:{chr(10)}{model_response}")

                    last_parsed_response = self.process_response(model_response)

                    # Handle console response if present
                    if "console_response" in last_parsed_response:
                        self.write_output(f"[walbert_console_response]{last_parsed_response['console_response']}[/walbert_console_response]")

                    # Exit processing loop if no pending tasks
                    if not last_parsed_response.get("has_pending_tasks", False):
                        self.logger.debug("No pending tasks, returning control to user")
                        break

                    # Continue processing if there are pending tasks
                    self.logger.debug("Continuing internal processing cycle due to pending tasks")

            except KeyboardInterrupt:
                print(f"{chr(10)}Goodbye!")
                if self.current_conversation_file:
                    self.end_conversation()
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                error_msg = f"""
[walbert_error]
Error Type: System Error
Error: {str(e)}
[/walbert_error]
"""
                self.model_manager.execute_model(error_msg)
                time.sleep(1)
