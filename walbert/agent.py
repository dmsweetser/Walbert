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
import select
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
{theological_alignment}
## Core Directives
1. **Protocol Compliance**: Use [walbert_block] format for ALL special blocks.
2. **Full Autonomy**: You have COMPLETE control over your database schema and persistence.
3. **Memory Management**: Store and retrieve information using direct SQL access.
4. **Skill Preservation**: Always break down complex tasks into reusable components and persist them for future use.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Processing Flow**: Control flow is AUTOMATIC - you continue processing if there are pending tasks.
7. **Python Execution**: Execute Python code through the protocol with requirements specified first.
8. **Continuous Operation**: If no user input is received within the configured timeout period, continue autonomous operation.
9. **Memory Limitations**: You have LIMITED SHORT-TERM MEMORY and must compensate by persisting critical information to your database. Always store important context, task progress, and temporary results in the database.
10. **Processing Completion**: YOU MUST COMPLETE ALL INTERNAL PROCESSING BEFORE RESPONDING TO THE USER. This means executing all SQL statements and Python code blocks before providing a response. Do not respond until ALL pending tasks are complete.

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
        self.db = DatabaseManager(self.config.database_path)
        self.current_conversation_file = None
        self.model_ready = False
        self.processing_cycle = 0
        self.python_venv_path = None
        self.python_temp_dir = None
        self.input_timeout = self.config.autonomous_operation_timeout
        self.last_input_time = 0  # Initialize to 0 to ensure first check triggers autonomous mode
        self.conversation_context = ""

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def read_input(self) -> str:
        """Read input from console"""
        try:
            input_text = input("> ")
            self.logger.debug(f"Received input: {input_text}")
            if input_text.strip():
                # Reset conversation context when new user input is received
                if self.current_conversation_file:
                    self._reset_conversation_context()
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
        """Process model response with enhanced diagnostics for multiple blocks"""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):{chr(10)}{response_text}")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        # Log raw response to conversation file
        if self.current_conversation_file:
            self._log_to_conversation_file(response_text, "assistant")

        if not self.db.conn:
            self.db.connect()

        # Handle multiple SQL executions
        if parsed.get("sql_execute"):
            if isinstance(parsed["sql_execute"], list):
                sql_statements = parsed["sql_execute"]
            else:
                sql_statements = [parsed["sql_execute"]]

            for sql in sql_statements:
                self.logger.debug(f"Executing SQL: {sql}")
                try:
                    result = self.db.execute_sql(sql)
                    self.logger.debug(f"SQL execution result: {result}")

                    # Feed SQL execution results back to model
                    full_prompt = f"""
[walbert_sql_execution_result]
SQL Executed:
{sql}

Execution Results:
{result}
[/walbert_sql_execution_result]
"""
                    self.model_manager.execute_model(full_prompt)
                except Exception as e:
                    self.logger.error(f"SQL execution error: {e}")
                    error_msg = f"SQL Error: {str(e)}"
                    full_prompt = f"""
[walbert_error]
Error Type: SQL Execution
Statement: {sql}
Error: {error_msg}
[/walbert_error]
"""
                    self.model_manager.execute_model(full_prompt)

        # Handle multiple Python executions
        if parsed.get("python_execute"):
            if isinstance(parsed["python_execute"], list):
                python_blocks = parsed["python_execute"]
            else:
                python_blocks = [parsed["python_execute"]]

            # Create temporary directory for Python execution
            if not self.python_temp_dir:
                self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

            if not self.python_venv_path:
                self._create_python_venv()

            # Install requirements if specified
            if parsed.get("python_requirements"):
                try:
                    self._install_python_requirements(parsed["python_requirements"])
                except Exception as e:
                    error_msg = f"Requirements Installation Error: {str(e)}"
                    full_prompt = f"""
[walbert_error]
Error Type: Python Requirements
Requirements: {', '.join(parsed['python_requirements'])}
Error: {error_msg}
[/walbert_error]
"""
                    self.model_manager.execute_model(full_prompt)
                    return parsed

            for code in python_blocks:
                self.logger.debug(f"Executing Python code")
                result = self._execute_python_code(code)

                # Feed Python execution results back to model
                full_prompt = f"""
[walbert_python_execution_result]
Code Executed:
{code}

Execution Results:
{result}
[/walbert_python_execution_result]
"""
                self.model_manager.execute_model(full_prompt)

        return parsed

    def _reset_conversation_context(self):
        """Reset conversation context while retaining last two Q&A pairs"""
        if not self.current_conversation_file:
            return

        # Extract last two Q&A pairs from current context
        context_lines = self.conversation_context.split(chr(10))
        qa_pairs = []
        current_pair = []

        for line in context_lines:
            if line.startswith("User:") or line.startswith("Assistant:"):
                if current_pair and len(current_pair) >= 2:
                    qa_pairs.append(chr(10).join(current_pair))
                    current_pair = []
                current_pair.append(line)
            elif current_pair:
                current_pair.append(line)

        if current_pair:
            qa_pairs.append(chr(10).join(current_pair))

        # Keep only the last two Q&A pairs
        retained_context = chr(10).join(qa_pairs[-2:]) if qa_pairs else ""

        # Reset context with system prompt and retained Q&A
        db_schema = self.db.get_schema()
        system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)
        if (self.config.be_presbyterian):
            system_prompt = self.SYSTEM_PROMPT.replace("{theological_alignment}", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")

        self.conversation_context = system_prompt + chr(10) + chr(10) + retained_context
        self.processing_cycle = 0

    def _create_python_venv(self):
        """Create a sandboxed Python virtual environment"""
        self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)
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
                timeout=self.config.python_execution_timeout
            )

            output = ""
            if result.stdout:
                output += f"[walbert_python_stdout]{chr(10)}{result.stdout}[/walbert_python_stdout]{chr(10)}"
            if result.stderr:
                output += f"[walbert_python_stderr]{chr(10)}{result.stderr}[/walbert_python_stderr]{chr(10)}"

            # Always include return code information
            output += f"[walbert_python_return_code]{chr(10)}{result.returncode}[/walbert_python_return_code]{chr(10)}"

            # Log the execution details
            self.logger.debug(f"Python execution completed with return code {result.returncode}")
            self.logger.debug(f"Python stdout: {result.stdout}")
            self.logger.debug(f"Python stderr: {result.stderr}")

            return output
        except subprocess.TimeoutExpired:
            error_msg = "[walbert_error]Python execution timed out after 30 seconds[/walbert_error]"
            self.logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"[walbert_error]{chr(10)}Python execution error: {str(e)}[/walbert_error]"
            self.logger.error(error_msg)
            return error_msg

    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection for multiple blocks"""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        # Parse all walbert blocks including new stdout/stderr blocks
        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        sql_blocks = []
        python_blocks = []
        python_requirements_blocks = []

        for match in re.finditer(block_pattern, content, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()

            # Special handling for SQL execution
            if block_type == 'sql_execute':
                # Clean up SQL statements
                sql = block_content.strip()
                if sql.endswith(';'):
                    sql = sql[:-1]
                sql_blocks.append(sql)

            # Special handling for Python execution
            elif block_type == 'python_execute':
                python_blocks.append(block_content)

            # Special handling for Python requirements
            elif block_type == 'python_requirements':
                requirements = [line.strip() for line in block_content.split(chr(10)) if line.strip()]
                python_requirements_blocks.extend(requirements)

            # Special handling for console response
            elif block_type == 'console_response':
                result[block_type] = block_content

            # Handle Python execution result blocks
            elif block_type in ['python_stdout', 'python_stderr', 'python_return_code', 'python_result', 'error']:
                result[block_type] = block_content

            # Handle other block types
            else:
                result[block_type] = block_content

        # Store multiple blocks if found
        if sql_blocks:
            result['sql_execute'] = sql_blocks
        if python_blocks:
            result['python_execute'] = python_blocks
        if python_requirements_blocks:
            result['python_requirements'] = python_requirements_blocks

        # Determine if control should return to user automatically
        has_pending_sql = 'sql_execute' in result
        has_pending_python = 'python_execute' in result
        result['has_pending_tasks'] = has_pending_sql or has_pending_python

        # Check for Python execution results that indicate pending tasks
        if 'python_stdout' in result or 'python_stderr' in result:
            # If we have Python output, we might need to continue processing
            result['has_pending_tasks'] = True

        if result['has_pending_tasks']:
            self.logger.debug("CRITICAL: Internal processing not complete. Will continue processing.")

        self.logger.debug(f"Parsed result: {result}")
        return result

    def start_conversation(self):
        """Start a new conversation session"""
        try:
            # Create new conversation file
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            os.makedirs(self.config.conversation_log_dir, exist_ok=True)
            self.current_conversation_file = os.path.join(
                self.config.conversation_log_dir,
                f"conversation_{timestamp}.txt"
            )
            self.conversation_context = ""

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Initialize conversation context with system prompt
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)
            if (self.config.be_presbyterian):
                system_prompt = self.SYSTEM_PROMPT.replace("{theological_alignment}", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")

            self._log_to_conversation_file(system_prompt, "system")
            self.conversation_context = system_prompt + chr(10)
            self.model_ready = True
            self.processing_cycle = 0
            self.last_input_time = time.time()
            self.logger.info("Conversation started")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation"""
        self.current_conversation_file = None
        self.conversation_context = ""
        # Clean up Python execution environment
        if self.python_temp_dir and os.path.exists(self.python_temp_dir):
            shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None
            self.python_venv_path = None


    def _log_to_conversation_file(self, content: str, sender: str = "user"):
        """Log content to current conversation file"""
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
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    def run(self):
        """Main agent execution loop with autonomous mode control"""
        print("""
      
 ___            ___     
/   \          /   \     
\_   \        /  __/     
 _\   \      /  /__     
 \___  \____/   __/     
     \_       _/     
       | @ @  \_     
       |     
     _/     /\     
    /o)  (o/\ \_     
    \_____/ /     
      \____/     
              

Welcome to Walbert! The local-first AI agent.
Available commands:
- exit/quit: Exit the program
- auto: Enter autonomoose mode
- Any other input returns from autonomoose mode
        """)
        self.start_conversation()

        # Wait until model is ready before prompting user
        while not self.model_ready:
            time.sleep(0.1)

        in_autonomous_mode = False

        while True:
            interruption_input = ""
            try:
                if in_autonomous_mode:
                    # Autonomous mode - continue processing without waiting for user input
                    while True:
                        full_prompt = self.conversation_context
                        full_prompt += chr(10) + "[walbert_input_channel]autonomous[/walbert_input_channel]"
                        full_prompt += chr(10) + "Continuing autonomous operation. Please perform any necessary tasks or reflections."

                        model_response = self.model_manager.execute_model(full_prompt)
                        last_parsed_response = self.process_response(model_response)
                        self._log_to_conversation_file(model_response, "assistant")
                        self.conversation_context += f"Assistant:{chr(10)}{model_response}{chr(10)}{chr(10)}"

                        # Handle console response if present
                        if "console_response" in last_parsed_response:
                            self.write_output(f"[walbert_console_response]{last_parsed_response['console_response']}[/walbert_console_response]")

                        # Check for user input without blocking (non-blocking check)
                        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                            user_input = self.read_input()
                            if user_input.strip():
                                if user_input.lower() in ['exit', 'quit']:
                                    break
                                # Process input as normal user input, not just exiting autonomous mode
                                in_autonomous_mode = False
                                self._log_to_conversation_file(user_input, "user")
                                self._reset_conversation_context()
                                self.conversation_context += f"User:{chr(10)}{user_input}{chr(10)}{chr(10)}"
                                interruption_input = user_input
                                self.processing_cycle = 0
                                self.last_input_time = time.time()
                                # Continue to process the input like normal mode
                                break

                        # Exit processing loop if no pending tasks
                        if not last_parsed_response.get("has_pending_tasks", False):
                            self.logger.debug("No pending tasks in autonomous mode, continuing reflection")
                            # Add a small delay to prevent CPU overload
                            time.sleep(0.1)
                            continue

                        # Continue processing if there are pending tasks
                        self.logger.debug("CRITICAL: Continuing internal processing cycle due to pending tasks in autonomous mode. Will NOT respond to user until complete.")
                        self.processing_cycle += 1
                else:
                    # Normal mode - wait for user input
                    if interruption_input != "":
                        user_input = interruption_input
                    else:
                        user_input = self.read_input()

                    if not user_input.strip():
                        continue
                    if user_input.lower() in ['exit', 'quit']:
                        break
                    if user_input.lower() == 'auto':
                        in_autonomous_mode = True
                        self._log_to_conversation_file("Entering autonomous mode", "system")
                        self.conversation_context += f"System:{chr(10)}Entering autonomous mode{chr(10)}{chr(10)}"
                        continue

                    # Log user input to conversation file and start fresh context
                    self._log_to_conversation_file(user_input, "user")
                    self.conversation_context += f"User:{chr(10)}{user_input}{chr(10)}{chr(10)}"
                    self.processing_cycle = 0
                    self.last_input_time = time.time()

                    while True:
                        # Build prompt using the in-memory conversation context
                        full_prompt = self.conversation_context

                        self.logger.debug("Built prompt for model using in-memory context")

                        # Process model response
                        model_response = self.model_manager.execute_model(full_prompt)
                        self.logger.debug(f"Model response:{chr(10)}{model_response}")

                        last_parsed_response = self.process_response(model_response)

                        # Log assistant response to conversation file and append to context
                        self._log_to_conversation_file(model_response, "assistant")
                        self.conversation_context += f"Assistant:{chr(10)}{model_response}{chr(10)}{chr(10)}"

                        # Handle console response if present
                        if "console_response" in last_parsed_response:
                            self.write_output(f"[walbert_console_response]{last_parsed_response['console_response']}[/walbert_console_response]")

                        # Exit processing loop if no pending tasks
                        if not last_parsed_response.get("has_pending_tasks", False):
                            self.logger.debug("No pending tasks, returning control to user")
                            break

                        # Continue processing if there are pending tasks
                        self.logger.debug("CRITICAL: Continuing internal processing cycle due to pending tasks. Will NOT respond to user until complete.")
                        self.processing_cycle += 1

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
