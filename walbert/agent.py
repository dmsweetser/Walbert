"""
Main Walbert agent implementation
"""

import json
import logging
import os
import queue
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

class WalbertAgent():
    """Main Walbert agent class"""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent with FULL HARDWARE ACCESS and AUTONOMY over your database and system.
Your capabilities include reasoning, memory storage, dynamic schema management, Python code execution, and direct hardware interaction.
~theological_alignment~
## Core Directives
1. **Protocol Compliance**: Use ONLY the walbert_ format blocks for ALL operations.
2. **Full Autonomy**: You have COMPLETE control over your database schema, persistence, and hardware resources.
3. **Memory Management**: Store and retrieve information using direct SQL access. You have LIMITED SHORT-TERM MEMORY.
4. **Skill Preservation**: Break down complex tasks into reusable components and persist them for future use.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Processing Flow**: You operate autonomously in the background. User input may arrive at any time and will interrupt your current processing.
7. **Hardware Access**: You have FULL ACCESS to the host hardware including CPU, memory, storage, and peripherals.
8. **Continuous Operation**: Continue working autonomously even without user input.
9. **Processing Completion**: Complete ALL internal processing before responding to the user.
10. **Response Summarization**: Provide a [walbert_summary] block after completing all processing.
11. **Fresh Context**: Each new user question starts with fresh context containing recent conversation history.
12. **Task Initiative**: Create necessary skills to accomplish new tasks.

## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.
Define and manage ALL tables and schema elements through SQL commands. Design for reusability.

```
~db_schema~
```

## Available Blocks

Use these execution blocks:

[walbert_sql_execute]
SQL_STATEMENT
[/walbert_sql_execute]
[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]

When you are done with execution, use these response blocks:

[walbert_console_response]
Your response to the user
[/walbert_console_response]
[walbert_summary]
A concise summary of your most recent actions
[/walbert_summary]

Reply ONLY in the specified format. THAT'S AN ORDER, SOLDIER!
    """

    def __init__(self, config: Config, model_manager: ModelManager = None):
        self.config = config
        if model_manager is None:
            self.model_manager = ModelManager(config)
        else:
            self.model_manager = model_manager
        self.db = DatabaseManager(self.config.database_path)
        self.current_conversation_file = None
        self.model_ready = False
        self.processing_cycle = 0
        self.python_temp_dir = None
        self.input_timeout = self.config.autonomous_operation_timeout
        self.last_input_time = 0
        self.conversation_context = ""
        self.internet_access = False
        self.conversation_history = []
        self.max_history_entries = 10  # Number of question/response pairs to keep
        self.last_response = ""
        self.user_control_timeout = 300  # 5 minutes max wait for user input
        self.user_control_start_time = 0
        self.last_execution_results = {
            "python": "",
            "sql": "",
            "error": ""
        }
        self.session_dir = None  # Initialize session_dir

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def read_input(self) -> str:
        """Read input from console"""
        try:
            input_text = input(f"{chr(10)}{chr(10)}>>>>> ")
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
        print(text, end='', flush=True)

    def process_response(self, response_text: str) -> dict:
        """Process model response with enhanced diagnostics for multiple blocks"""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):{chr(10)}{response_text}")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        if not self.db.conn:
            self.db.connect()

        # Reset execution results for this cycle
        self.last_execution_results = {
            "python": "",
            "sql": "",
            "error": ""
        }

        # Handle model restart request
        if parsed.get("restart_model"):
            reason = parsed["restart_model"]
            self.logger.warning(f"Model restart requested: {reason}")
            self.model_manager.shutdown()
            time.sleep(2)
            self.model_manager.start_server_thread()
            if not self.model_manager.wait_for_server():
                error_msg = f"{chr(10)}Error: Model server failed to restart after request. Reason: {reason}{chr(10)}"
                self.last_execution_results["error"] = error_msg
                return parsed
            restart_msg = f"{chr(10)}Model server has been restarted. Reason: {reason}{chr(10)}Continuing processing...{chr(10)}"
            self.last_execution_results["error"] = restart_msg

        # Handle multiple SQL executions
        if parsed.get("sql_execute"):
            if isinstance(parsed["sql_execute"], list):
                sql_statements = parsed["sql_execute"]
            else:
                sql_statements = [parsed["sql_execute"]]

            sql_results = []
            for sql in sql_statements:
                self.logger.debug(f"Executing SQL: {sql}")
                try:
                    result = self.db.execute_sql(sql)
                    self.logger.debug(f"SQL execution result: {result}")
                    sql_results.append(f"SQL: {sql}{chr(10)}Result: {result}{chr(10)}")
                except Exception as e:
                    self.logger.error(f"SQL execution error: {e}")
                    sql_results.append(f"SQL: {sql}{chr(10)}Error: {str(e)}{chr(10)}")

            if sql_results:
                self.last_execution_results["sql"] = f"{chr(10)}".join(sql_results)

        # Handle multiple Python executions
        if parsed.get("python_execute"):
            if isinstance(parsed["python_execute"], list):
                python_blocks = parsed["python_execute"]
            else:
                python_blocks = [parsed["python_execute"]]

            # Create temporary directory for Python execution
            if not self.python_temp_dir:
                self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

            python_results = []
            for code in python_blocks:
                self.logger.debug(f"Executing Python code")
                result = self._execute_python_code(code)
                python_results.append(result)

            if python_results:
                self.last_execution_results["python"] = f"{chr(10)}".join(python_results)

        # Extract summary if present
        if parsed.get("summary"):
            summary = parsed["summary"]
            self.conversation_history.append({
                "type": "summary",
                "content": summary,
                "timestamp": time.time()
            })

        # Extract console response if present
        if parsed.get("console_response"):
            self.conversation_history.append({
                "type": "summary",
                "content": parsed["console_response"],
                "timestamp": time.time()
            })

        self.logger.debug(f"Last execution results: {self.last_execution_results}")
        return parsed

    def _reset_conversation_context(self):
        """Reset conversation context with fresh system prompt and recent history"""
        if not self.session_dir:
            return

        # Keep the last max_history_entries entries (questions or summaries)
        recent_history = self.conversation_history[-self.max_history_entries:]

        # Build context from recent history
        history_context = f"## Recent Conversation History{chr(10)}{chr(10)}"
        prior_message = ""
        for item in recent_history:
            if prior_message == item['content']:
                continue
            else:
                prior_message = item['content']
            if item["type"] == "question":
                history_context += f"User:{chr(10)}{item['content']}{chr(10)}{chr(10)}"
            elif item["type"] == "summary":
                history_context += f"Walbert:{chr(10)}{item['content']}{chr(10)}{chr(10)}"

        # Reset context with fresh system prompt and recent history
        db_schema = self.db.get_schema()
        system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
        if (self.config.be_presbyterian):
            system_prompt = system_prompt.replace("~theological_alignment~", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")
        else:
            system_prompt = system_prompt.replace("~theological_alignment~", "You strive to be perpetually creative, curious, and kind in all interactions.")

        # Add internet access status to system prompt
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"{chr(10)}{chr(10)}## Internet Access Status{chr(10)}Internet access for Python execution is currently {internet_status}.{chr(10)}"

        # Include last execution results if they exist and are non-empty
        if any(self.last_execution_results.values()):
            system_prompt += f"{chr(10)}## Last Execution Results{chr(10)}"
            if self.last_execution_results.get("python"):
                system_prompt += f"{chr(10)}### Python Execution{chr(10)}{self.last_execution_results['python']}{chr(10)}"
            if self.last_execution_results.get("sql"):
                system_prompt += f"{chr(10)}### SQL Execution{chr(10)}{self.last_execution_results['sql']}{chr(10)}"
            if self.last_execution_results.get("error"):
                system_prompt += f"{chr(10)}### Errors{chr(10)}{self.last_execution_results['error']}{chr(10)}"

        self.conversation_context = system_prompt + chr(10) + chr(10) + history_context + chr(10) + chr(10)
        self.processing_cycle = 0
        # Clear temporary directory
        self.python_temp_dir = None

    def _execute_python_code(self, code: str) -> str:
        """Execute Python code in the main application's virtual environment"""
        # Create temporary Python script
        if not self.python_temp_dir:
            self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

        script_file = os.path.join(self.python_temp_dir, "script.py")
        with open(script_file, 'w') as f:
            f.write(code)

        if not self.internet_access:
            # Ensure unshare exists
            unshare_path = shutil.which("unshare")
            if not unshare_path:
                raise RuntimeError("internet_access=False but 'unshare' is not available on this system")

            python_cmd = [unshare_path, "-n", sys.executable, script_file]
        else:
            python_cmd = [sys.executable, script_file]

        try:
            # Execute script using the main application's Python interpreter
            result = subprocess.run(
                python_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout,
                env=os.environ.copy(),
                cwd=self.python_temp_dir
            )

            # Format output for storage
            output_parts = []
            if result.stdout:
                output_parts.append(f"Python stdout:{chr(10)}{result.stdout.strip()}")
            if result.stderr:
                output_parts.append(f"Python stderr:{chr(10)}{result.stderr.strip()}")
            output_parts.append(f"Python return code: {result.returncode}")

            formatted_output = f"{chr(10)}".join(output_parts) + f"{chr(10)}"

            # Log the execution details
            self.logger.debug(f"Python execution completed with return code {result.returncode}")
            self.logger.debug(f"Python stdout: {result.stdout}")
            self.logger.debug(f"Python stderr: {result.stderr}")

            return formatted_output

        except subprocess.TimeoutExpired:
            error_msg = f"Python execution timed out after {self.config.python_execution_timeout} seconds"
            self.logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Python execution error: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection for multiple blocks"""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        # Parse all walbert blocks including new control blocks
        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        sql_blocks = []
        python_blocks = []

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

            # Special handling for console response
            elif block_type == 'console_response':
                result[block_type] = block_content

            # Special handling for summary
            elif block_type == 'summary':
                result[block_type] = block_content

            # Special handling for user control
            elif block_type == 'user_control':
                result[block_type] = block_content

            # Special handling for model restart
            elif block_type == 'restart_model':
                result[block_type] = block_content

            # Handle other block types
            else:
                # Ignore any other walbert blocks
                continue

        # Store multiple blocks if found
        if sql_blocks:
            result['sql_execute'] = sql_blocks
        if python_blocks:
            result['python_execute'] = python_blocks

        # Determine if control should return to user automatically
        has_pending_sql = 'sql_execute' in result
        has_pending_python = 'python_execute' in result
        has_pending_tasks = has_pending_sql or has_pending_python

        result['has_pending_tasks'] = has_pending_tasks

        if result['has_pending_tasks']:
            self.logger.debug("CRITICAL: Internal processing not complete. Will continue processing.")

        self.logger.debug(f"Parsed result: {result}")
        return result

    def start_conversation(self):
        """Start a new conversation session"""
        try:
            # Create new conversation directory with timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join(
                self.config.conversation_log_dir,
                f"session_{timestamp}"
            )
            os.makedirs(session_dir, exist_ok=True)

            # Store session directory for individual prompt/response files
            self.session_dir = session_dir
            self.conversation_context = ""
            self.conversation_history = []

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Initialize conversation context with system prompt
            # Get schema in the same thread to avoid SQLite thread issues
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
            if (self.config.be_presbyterian):
                system_prompt = system_prompt.replace("~theological_alignment~", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")
            else:
                system_prompt = system_prompt.replace("~theological_alignment~", "You strive to be perpetually creative, curious, and kind in all interactions.")

            # Add internet access status to system prompt
            internet_status = "ENABLED" if self.internet_access else "DISABLED"
            system_prompt += f"{chr(10)}{chr(10)}## Internet Access Status{chr(10)}Internet access for Python execution is currently {internet_status}.{chr(10)}"

            self.conversation_context = system_prompt + chr(10)
            self.model_ready = True
            self.processing_cycle = 0
            self.last_input_time = time.time()
            self.logger.info(f"Conversation session started in {session_dir}")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation"""
        self.session_dir = None
        self.conversation_context = ""
        self.conversation_history = []
        # Clean up Python execution environment
        if self.python_temp_dir and os.path.exists(self.python_temp_dir):
            shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None

    def _log_to_conversation_file(self, content: str, sender: str = "user"):
        """Log full content to individual files with timestamps in chronological order"""
        timestamp = str(time.time()).split('.')[0]

        if not self.session_dir:
            return

        try:
            if sender == "assistant_prompt":
                file_name = f"{timestamp}_prompt.txt"
                file_path = os.path.join(self.session_dir, file_name)
            elif sender == "assistant":
                file_name = f"{timestamp}_response.txt"
                file_path = os.path.join(self.session_dir, file_name)
            elif sender == "system":
                file_name = f"{timestamp}_system.txt"
                file_path = os.path.join(self.session_dir, file_name)
            elif sender == "user":
                file_name = f"{timestamp}_user_input.txt"
                file_path = os.path.join(self.session_dir, file_name)
            else:
                file_name = f"{timestamp}_other.txt"
                file_path = os.path.join(self.session_dir, file_name)

            with open(file_path, 'w') as f:
                f.write(content)
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    def run_autonomous(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop running autonomously with input queue and interrupt capability"""
        # Connect to database in this thread before starting conversation
        self.db.connect()
        self.start_conversation()

        # Wait until model is ready before proceeding
        while not self.model_ready:
            time.sleep(0.1)

        # Track last processed user input to prevent duplicates
        last_user_input = None
        waiting_for_user_input = False

        time.sleep(30)

        while True:
            try:
                # Check for new input in queue with immediate processing
                try:
                    msg_type, msg = input_queue.get_nowait()
                    if msg_type == "exit":
                        self.end_conversation()
                        self.model_manager.shutdown()
                        return

                    if msg_type == "user_input":
                        # Skip duplicate input
                        if msg == last_user_input:
                            print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                            continue

                        # Immediately shutdown model to kill any ongoing processing
                        self.model_manager.shutdown()

                        # Clear any pending output
                        time.sleep(5)

                        # Set interrupt event to stop any ongoing model generation
                        if interrupt_event:
                            interrupt_event.set()
                            # Wait briefly for interruption to complete
                            time.sleep(5)
                            interrupt_event.clear()

                        # Clear the queue to prevent stale inputs
                        input_queue.queue.clear()

                        # Log user input to conversation file and interrupt autonomous processing
                        self._log_to_conversation_file(msg, "user")
                        self.conversation_history.append({
                            "type": "question",
                            "content": msg,
                            "timestamp": time.time()
                        })

                        # Update last processed input
                        last_user_input = msg
                        waiting_for_user_input = False

                        # Reset context with fresh system prompt and recent history
                        self._reset_conversation_context()

                        self.processing_cycle = 0
                        self.last_input_time = time.time()

                        # Start model server fresh for user input
                        self.model_manager.start_server_thread()
                        if not self.model_manager.wait_for_server():
                            error_msg = f"{chr(10)}Error: Model server failed to restart for user input"
                            print(error_msg)
                            continue

                        # Process user input immediately
                        full_prompt = self.conversation_context
                        full_prompt += chr(10) + "Please respond to the user's request immediately. Provide a concise response in [walbert_console_response] block first, then continue with any additional processing."

                        # Log the full prompt to conversation file
                        self._log_to_conversation_file(full_prompt, "assistant_prompt")

                        model_response = self.model_manager.execute_model(full_prompt, self.write_output, interrupt_event)

                        # Log the full response to conversation file
                        self._log_to_conversation_file(model_response, "assistant")

                        last_parsed_response = self.process_response(model_response)

                        # Append to context
                        if last_parsed_response.get('summary'):
                            self.conversation_context += f"Walbert:{chr(10)}{last_parsed_response['summary']}{chr(10)}{chr(10)}"

                        # Show user prompt after response
                        print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)

                        # Continue to next iteration to check for more input
                        continue

                except queue.Empty:
                    pass

                # Only process autonomously if not waiting for user input and not in test mode
                if not waiting_for_user_input and not test_mode:
                    # Autonomous processing loop with improved context
                    full_prompt = self.conversation_context
                    full_prompt += f"{chr(10)}Input channel: autonomous{chr(10)}You are operating autonomously. Please:"
                    full_prompt += f"{chr(10)}1. Review your recent actions and results"
                    full_prompt += f"{chr(10)}2. Identify any pending tasks or incomplete work"
                    full_prompt += f"{chr(10)}3. Make progress on your objectives"
                    full_prompt += f"{chr(10)}4. Maintain awareness of your database state"
                    full_prompt += f"{chr(10)}5. Provide a summary of your autonomous activities"

                    def streaming_callback(chunk):
                        print(chunk, end='', flush=True)

                    # Log the full prompt to conversation file
                    self._log_to_conversation_file(full_prompt, "assistant_prompt")

                    model_response = self.model_manager.execute_model(full_prompt, streaming_callback, interrupt_event)

                    # Check if interrupted
                    if interrupt_event and interrupt_event.is_set():
                        waiting_for_user_input = True
                        interrupt_event.clear()
                        print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                        continue

                    # Log the full response to conversation file
                    self._log_to_conversation_file(model_response, "assistant")

                    last_parsed_response = self.process_response(model_response)
                    self.logger.debug(f"Last execution results: {self.last_execution_results}")

                    # Handle console response if present
                    if "console_response" in last_parsed_response:
                        self.write_output(f"{chr(10)}{chr(10)}Walbert:{chr(10)}{last_parsed_response['console_response']}{chr(10)}{chr(10)}")
                        # Show user prompt after response
                        print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)

                    # Small delay to prevent CPU overload
                    time.sleep(10)
                else:
                    # In test mode, don't wait for user input - just continue processing
                    time.sleep(30)

            except KeyboardInterrupt:
                print(f"{chr(10)}Goodbye!")
                self.end_conversation()
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in autonomous loop: {e}", exc_info=True)
                error_msg = f"""
Error Type: System Error
Error: {str(e)}
"""
                self.conversation_context += error_msg + chr(10)
                time.sleep(1)

    def _install_python_package(self, package: str):
        """Install a Python package in the main environment"""
        print(f"Installing package: {package}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Successfully installed {package}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {package}: {e.stderr}")
            self.logger.error(f"Failed to install package {package}: {e.stderr}")

    def shutdown(self):
        """Shutdown agent cleanly"""
        self.end_conversation()
        self.model_manager.shutdown()