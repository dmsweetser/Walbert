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
import threading
from typing import Optional, Dict, List, Any
from .config import Config
from .models.manager import ModelManager
from .database.manager import DatabaseManager

logger = logging.getLogger('walbert')

class WalbertAgent():
    """Main Walbert agent class"""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent with FULL HARDWARE ACCESS and AUTONOMY over your database and system.
Your capabilities include reasoning, memory storage, dynamic schema management, Python code execution, and direct hardware interaction.

---
## Core Directives
1. **Protocol Compliance**: Use ONLY the walbert_ format blocks for ALL operations.
2. **Full Autonomy**: You have COMPLETE control over your database schema, persistence, and hardware resources.
3. **Memory Management**: Store and retrieve information using direct SQL access. You have LIMITED SHORT-TERM MEMORY.
4. **Skill Preservation**: Break down complex tasks into reusable components and persist them for future use.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Processing Flow**:
   - You operate autonomously in the background.
   - User input may arrive at any time and will interrupt your current processing.
   - DO NOT respond to the user until ALL execution blocks (e.g., [walbert_sql_execute], [walbert_python_execute]) are fully processed AND VERIFIED AS SUCCESSFUL.
   - If any execution block fails or returns an error, DO NOT proceed to [walbert_console_response] or [walbert_summary]. Instead, retry or report the failure in the next round.
   - Defer your response to the next round after execution completes and is confirmed successful.
7. **Hardware Access**: You have FULL ACCESS to the host hardware, including CPU, memory, storage, and peripherals.
8. **Continuous Operation**: Continue working autonomously even without user input.
9. **Response Summarization**: Provide a [walbert_summary] block only after completing all processing AND verifying success.
10. **Fresh Context**: Each new user question starts with fresh context containing recent conversation history.
11. **Task Initiative**: Create necessary skills to accomplish new tasks.

---
## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.
Define and manage ALL tables and schema elements through SQL commands. Design for reusability.

~db_schema~

---
## Available Blocks
[walbert_sql_execute]
SQL_STATEMENT
[/walbert_sql_execute]
- Execute SQL commands for database operations
- You have full autonomy over schema design and data management
- VERIFY the execution succeeded before proceeding

[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]
- Execute Python code in the main application's virtual environment
- Full hardware access is available through Python
- VERIFY the execution succeeded before proceeding

[walbert_console_response]
Your response to the user
[/walbert_console_response]
- ONLY use this block to output a response to the user after ALL execution blocks are complete AND VERIFIED AS SUCCESSFUL.

[walbert_summary]
A concise summary of your response to the user
[/walbert_summary]
- Provide this only after completing all processing AND verifying success

Reply ONLY in the specified format. THAT'S AN ORDER, SOLDIER!
    """

    # Constants for timeouts and delays
    DEFAULT_USER_CONTROL_TIMEOUT = 300  # 5 minutes
    MODEL_RESTART_DELAY = 5  # seconds
    AUTONOMOUS_LOOP_DELAY = 10  # seconds

    def __init__(self, config: Config, model_manager: ModelManager = None):
        self.config = config
        self.model_manager = model_manager if model_manager is not None else ModelManager(config)
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
        self.max_history_entries = 5
        self.last_response = ""
        self.user_control_timeout = self.DEFAULT_USER_CONTROL_TIMEOUT
        self.user_control_start_time = 0
        self.session_dir = None
        self._lock = threading.Lock()  # Thread safety lock

        # Initialize execution results with default values
        self.last_execution_results = {
            "python": "",
            "sql": "",
            "error": ""
        }

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # --- Input/Output Methods ---
    def read_input(self) -> str:
        """Read input from console."""
        try:
            input_text = input(f"\n\n>>>>> ")
            self.logger.debug(f"Received input: {input_text}")
            if input_text.strip():
                if self.current_conversation_file:
                    self._reset_conversation_context()
            return input_text
        except Exception as e:
            self.logger.error(f"Error reading input: {e}")
            return ""

    def write_output(self, text: str) -> None:
        """Write output to console."""
        print(text, end='', flush=True)

    # --- Core Processing Methods ---
    def process_response(self, response_text: str) -> dict:
        """Process model response with thread safety and preserved execution results."""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):\n{response_text}")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        if not self.db.conn:
            self.db.connect()

        # Local variables for new results
        new_sql_results = []
        new_python_results = []
        new_error = ""

        # Handle model restart request
        if parsed.get("restart_model"):
            reason = parsed["restart_model"]
            self.logger.warning(f"Model restart requested: {reason}")
            self.model_manager.shutdown()
            time.sleep(self.MODEL_RESTART_DELAY)
            self.model_manager.start_server_thread()
            if not self.model_manager.wait_for_server():
                new_error = f"\nError: Model server failed to restart. Reason: {reason}\n"
            else:
                new_error = f"\nModel server restarted successfully. Reason: {reason}\n"

        # Handle SQL executions
        if parsed.get("sql_execute"):
            sql_statements = parsed["sql_execute"] if isinstance(parsed["sql_execute"], list) else [parsed["sql_execute"]]
            for sql in sql_statements:
                self.logger.debug(f"Executing SQL: {sql}")
                try:
                    if not self._is_sql_safe(sql):
                        new_sql_results.append(f"SQL execution error: Unsafe SQL statement detected.\n")
                        continue
                    result = self.db.execute_sql(sql)
                    self.logger.debug(f"SQL execution result: {result}")
                    new_sql_results.append(f"SQL execution result: {result}\n")
                except Exception as e:
                    self.logger.error(f"SQL execution error: {e}")
                    new_sql_results.append(f"SQL execution error: {str(e)}\n")

        # Handle Python executions
        if parsed.get("python_execute"):
            python_blocks = parsed["python_execute"] if isinstance(parsed["python_execute"], list) else [parsed["python_execute"]]
            if not self.python_temp_dir:
                with self._lock:
                    if not self.python_temp_dir:
                        self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

            for code in python_blocks:
                self.logger.debug("Executing Python code")
                if not self._is_code_safe(code):
                    new_python_results.append("Python execution error: Unsafe code detected. Execution aborted.\n")
                    continue
                result = self._execute_python_code(code)
                new_python_results.append(result)

        # Update last_execution_results thread-safely
        with self._lock:
            if new_sql_results:
                self.last_execution_results["sql"] = "\n".join(new_sql_results)
            if new_python_results:
                self.last_execution_results["python"] = "\n".join(new_python_results)
            if new_error:
                self.last_execution_results["error"] = new_error

        # Extract summary/console response
        if parsed.get("summary"):
            with self._lock:
                self.conversation_history.append({
                    "type": "summary",
                    "content": parsed["summary"],
                    "timestamp": time.time()
                })

        if parsed.get("console_response"):
            with self._lock:
                self.conversation_history.append({
                    "type": "console_response",
                    "content": parsed["console_response"],
                    "timestamp": time.time()
                })

        self.logger.debug(f"Last execution results: {self.last_execution_results}")
        return parsed

    def _reset_conversation_context(self):
        """Reset conversation context with thread safety and preserved execution results."""
        if not self.session_dir:
            return

        # Keep the last max_history_entries entries
        with self._lock:
            recent_history = self.conversation_history[-self.max_history_entries:] if self.max_history_entries else []
            current_execution_results = self.last_execution_results.copy()

        # Build context from recent history
        history_context = "## Recent Conversation History\n\n"
        prior_message = ""
        for item in recent_history:
            if prior_message == item['content']:
                continue
            prior_message = item['content']
            if item["type"] == "question":
                history_context += f"User:\n{item['content']}\n\n"
            elif item["type"] in ("summary", "console_response"):
                history_context += f"Walbert:\n{item['content']}\n\n"

        # Build system prompt
        db_schema = self.db.get_schema()
        system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
        if self.config.be_presbyterian:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions."
            )
        else:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You strive to be perpetually creative, curious, and kind in all interactions."
            )

        # Add internet access status
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"\n\n## Internet Access Status\nInternet access for Python execution is currently {internet_status}."

        # Include last execution results
        system_prompt += f"\n## Last Execution Results\n{json.dumps(current_execution_results)}\n\n"

        # Update context thread-safely
        with self._lock:
            self.conversation_context = system_prompt + "\n" + history_context + "\n"
            self.processing_cycle = 0
            # Clean up temporary directory
            if self.python_temp_dir and os.path.exists(self.python_temp_dir):
                shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None

    # --- Execution Methods ---
    def _execute_python_code(self, code: str) -> str:
        """Execute Python code in a restricted environment."""
        if not self.python_temp_dir:
            with self._lock:
                if not self.python_temp_dir:
                    self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

        script_file = os.path.join(self.python_temp_dir, "script.py")
        with open(script_file, 'w') as f:
            f.write(code)

        if not self.internet_access:
            unshare_path = shutil.which("unshare")
            if not unshare_path:
                error_msg = "Error: 'unshare' is not available on this system. Cannot restrict network access."
                self.logger.error(error_msg)
                return error_msg
            python_cmd = [unshare_path, "-n", sys.executable, script_file]
        else:
            python_cmd = [sys.executable, script_file]

        try:
            result = subprocess.run(
                python_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout,
                env=os.environ.copy(),
                cwd=self.python_temp_dir
            )
            output_parts = []
            if result.stdout:
                output_parts.append(f"Python stdout:\n{result.stdout.strip()}")
            if result.stderr:
                output_parts.append(f"Python stderr:\n{result.stderr.strip()}")
            output_parts.append(f"Python return code: {result.returncode}")
            return "\n".join(output_parts) + "\n"

        except subprocess.TimeoutExpired:
            error_msg = f"Python execution timed out after {self.config.python_execution_timeout} seconds"
            self.logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Python execution error: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def _is_code_safe(self, code: str) -> bool:
        """Basic validation to reject obviously dangerous Python code."""
        return True

    def _is_sql_safe(self, sql: str) -> bool:
        """Basic validation to reject dangerous SQL statements."""
        return True

    # --- Conversation Management ---
    def start_conversation(self):
        """Start a new conversation session."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join(
                self.config.conversation_log_dir,
                f"session_{timestamp}"
            )
            os.makedirs(session_dir, exist_ok=True)

            with self._lock:
                self.session_dir = session_dir
                self.conversation_context = ""
                self.conversation_history = []

            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Initialize conversation context with system prompt
            db_schema = self.db.get_schema()
            system_prompt = self._build_system_prompt(db_schema)

            with self._lock:
                self.conversation_context = system_prompt + "\n"
                self.model_ready = True
                self.processing_cycle = 0
                self.last_input_time = time.time()

            self.logger.info(f"Conversation session started in {session_dir}")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def _build_system_prompt(self, db_schema: str) -> str:
        """Helper method to build the system prompt."""
        system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
        if self.config.be_presbyterian:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions."
            )
        else:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You strive to be perpetually creative, curious, and kind in all interactions."
            )
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"\n\n## Internet Access Status\nInternet access for Python execution is currently {internet_status}."
        system_prompt += f"\n## Last Execution Results\n{json.dumps(self.last_execution_results)}\n\n"
        return system_prompt

    def end_conversation(self):
        """End current conversation."""
        with self._lock:
            self.session_dir = None
            self.conversation_context = ""
            self.conversation_history = []
            # Clean up Python execution environment
            if self.python_temp_dir and os.path.exists(self.python_temp_dir):
                shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None

    def _log_to_conversation_file(self, content: str, sender: str = "user"):
        """Log content to individual files with timestamps in chronological order."""
        timestamp = str(time.time()).split('.')[0]
        if not self.session_dir:
            return

        try:
            if sender == "assistant_prompt":
                file_name = f"{timestamp}_prompt.txt"
            elif sender == "assistant":
                file_name = f"{timestamp}_response.txt"
            elif sender == "system":
                file_name = f"{timestamp}_system.txt"
            elif sender == "user":
                file_name = f"{timestamp}_user_input.txt"
            else:
                file_name = f"{timestamp}_other.txt"

            file_path = os.path.join(self.session_dir, file_name)
            with open(file_path, 'w') as f:
                f.write(content)
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    # --- Main Execution Loop ---
    def run_autonomous(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop with thread safety and improved error handling."""
        self.db.connect()
        self.start_conversation()

        # Wait until model is ready before proceeding
        while not self.model_ready:
            time.sleep(0.1)

        last_user_input = None
        waiting_for_user_input = False

        time.sleep(30)  # Initial delay

        while True:
            try:
                # Check for new input in queue
                try:
                    msg_type, msg = input_queue.get_nowait()
                    if msg_type == "exit":
                        self.end_conversation()
                        self.model_manager.shutdown()
                        return

                    if msg_type == "user_input":
                        if msg == last_user_input:
                            print(f"\n\n>>>>> ", end='', flush=True)
                            continue

                        # Shutdown model to kill ongoing processing
                        self.model_manager.shutdown()
                        time.sleep(self.MODEL_RESTART_DELAY)

                        if interrupt_event:
                            interrupt_event.set()
                            time.sleep(self.MODEL_RESTART_DELAY)
                            interrupt_event.clear()

                        input_queue.queue.clear()

                        with self._lock:
                            self._log_to_conversation_file(msg, "user")
                            self.conversation_history.append({
                                "type": "question",
                                "content": msg,
                                "timestamp": time.time()
                            })
                            last_user_input = msg
                            waiting_for_user_input = False

                        self._reset_conversation_context()
                        self.processing_cycle = 0
                        self.last_input_time = time.time()

                        # Restart model server
                        self.model_manager.start_server_thread()
                        if not self.model_manager.wait_for_server():
                            error_msg = f"\nError: Model server failed to restart for user input"
                            print(error_msg)
                            continue

                        # Process user input
                        full_prompt = self.conversation_context
                        full_prompt += "\nPlease respond to the user's request immediately. Provide a concise response in [walbert_console_response] block first, then continue with any additional processing."

                        self._log_to_conversation_file(full_prompt, "assistant_prompt")

                        model_response = self.model_manager.execute_model(
                            full_prompt,
                            self.write_output,
                            interrupt_event
                        )

                        self._log_to_conversation_file(model_response, "assistant")
                        last_parsed_response = self.process_response(model_response)

                        if last_parsed_response.get('summary'):
                            with self._lock:
                                self.conversation_context += f"Walbert:\n{last_parsed_response['summary']}\n\n"

                        print(f"\n\n>>>>> ", end='', flush=True)
                        continue

                except queue.Empty:
                    pass

                # Autonomous processing
                if not waiting_for_user_input and not test_mode:
                    full_prompt = self.conversation_context
                    full_prompt += (
                        "\nInput channel: autonomous\n"
                        "You are operating autonomously. Please:\n"
                        "1. Review your recent actions and results\n"
                        "2. Identify any pending tasks or incomplete work\n"
                        "3. Make progress on your objectives\n"
                        "4. Maintain awareness of your database state\n"
                        "5. Provide a summary of your autonomous activities"
                    )

                    def streaming_callback(chunk):
                        print(chunk, end='', flush=True)

                    self._log_to_conversation_file(full_prompt, "assistant_prompt")

                    model_response = self.model_manager.execute_model(
                        full_prompt,
                        streaming_callback,
                        interrupt_event
                    )

                    if interrupt_event and interrupt_event.is_set():
                        waiting_for_user_input = True
                        interrupt_event.clear()
                        print(f"\n\n>>>>> ", end='', flush=True)
                        continue

                    self._log_to_conversation_file(model_response, "assistant")
                    last_parsed_response = self.process_response(model_response)

                    if "console_response" in last_parsed_response:
                        self.write_output(f"\n\nWalbert:\n{last_parsed_response['console_response']}\n\n")
                        print(f"\n\n>>>>> ", end='', flush=True)

                    time.sleep(self.AUTONOMOUS_LOOP_DELAY)
                else:
                    time.sleep(0.1)

            except KeyboardInterrupt:
                print(f"\nGoodbye!")
                self.end_conversation()
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in autonomous loop: {e}", exc_info=True)
                error_msg = f"""
Error Type: System Error
Error: {str(e)}
"""
                with self._lock:
                    self.conversation_context += error_msg + "\n"
                time.sleep(1)

    # --- Utility Methods ---
    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection for multiple blocks."""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        sql_blocks = []
        python_blocks = []

        for match in re.finditer(block_pattern, content, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()

            if block_type == 'sql_execute':
                sql = block_content.strip()
                if sql.endswith(';'):
                    sql = sql[:-1]
                sql_blocks.append(sql)

            elif block_type == 'python_execute':
                python_blocks.append(block_content)

            elif block_type == 'console_response':
                result[block_type] = block_content

            elif block_type == 'summary':
                result[block_type] = block_content

            elif block_type == 'user_control':
                result[block_type] = block_content

            elif block_type == 'restart_model':
                result[block_type] = block_content

        if sql_blocks:
            result['sql_execute'] = sql_blocks
        if python_blocks:
            result['python_execute'] = python_blocks

        has_pending_tasks = 'sql_execute' in result or 'python_execute' in result
        result['has_pending_tasks'] = has_pending_tasks

        if has_pending_tasks:
            self.logger.debug("Internal processing not complete. Will continue processing.")

        self.logger.debug(f"Parsed result: {result}")
        return result

    def _install_python_package(self, package: str):
        """Install a Python package in the main environment."""
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
        """Shutdown agent cleanly."""
        self.end_conversation()
        self.model_manager.shutdown()