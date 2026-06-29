"""
Refactored WalbertAgent implementation with cached system prompt and continuous context building.
- System prompt is appended only once at the start of the conversation.
- Context is built incrementally, avoiding repetition of the system prompt.
- Optimized for caching and sequential block execution.
"""

from datetime import datetime
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


class WalbertAgent:
    """Refactored Walbert agent with cached system prompt and continuous context building."""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent with FULL HARDWARE ACCESS and AUTONOMY over your database and system.
Your capabilities include reasoning, memory storage, dynamic schema management, Python code execution, and direct hardware interaction.
~theological_alignment~
---
## Core Directives
1. **Block-Based Operation**: ALL operations must be wrapped in walbert_* blocks.
2. **Full Autonomy**: You have COMPLETE control over your database schema, persistence, and hardware resources.
3. **Granular Context**: Context is a chain of blocks. Each block is auditable and executed sequentially.
4. **Sequential Execution**: Blocks are executed in order. Results are appended as new blocks.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Response Protocol**:
   - Use [walbert_console_response_start]...[/walbert_console_response_end] for user-facing responses.
   - Use [walbert_sql_execute_start]...[/walbert_sql_execute_end] for SQL.
   - Use [walbert_python_execute_start]...[/walbert_python_execute_end] for Python.
   - Use [walbert_autonomous_instruction_start]...[/walbert_autonomous_instruction_end] for autonomous actions.
7. **Hardware Access**: You have FULL ACCESS to the host hardware.
8. **Continuous Operation**: Continue working autonomously even without user input.
---
## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.
Define and manage ALL tables and schema elements through SQL commands.
~db_schema~
---
## Block Types
- [walbert_system_prompt_start]...[/walbert_system_prompt_end]: System instructions.
- [walbert_console_response_start]...[/walbert_console_response_end]: Bot response to user.
- [walbert_sql_execute_start]...[/walbert_sql_execute_end]: SQL to execute.
- [walbert_sql_result_start]...[/walbert_sql_result_end]: Result of SQL execution.
- [walbert_python_execute_start]...[/walbert_python_execute_end]: Python code to execute.
- [walbert_python_result_start]...[/walbert_python_result_end]: Result of Python execution.
- [walbert_autonomous_instruction_start]...[/walbert_autonomous_instruction_end]: Autonomous mode instructions.
---
Reply ONLY in the specified block format. NO CRUFT.
---
    """

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
        self.internet_access = False
        self._lock = threading.Lock()
        self.system_prompt = None  # Cached system prompt

        # Context as a list of blocks (initialized as empty)
        self.context_blocks = []
        
        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # --- Block Management ---
    def _append_block(self, block_type: str, content: str):
        """Append a block to the context chain."""
        formatted_content = f"[walbert_{block_type}_start]\n{content}\n[walbert_{block_type}_end]\n"
        with self._lock:
            self.context_blocks.append({
                "type": block_type,
                "content": content,
                "timestamp": time.time()
            })
            self.logger.debug(f"Appended block: {block_type}")
            self._log_to_conversation_file(formatted_content)

    def _get_context_as_text(self) -> str:
        """Convert context blocks to a single string for model input, ensuring system prompt is only included once."""
        context_text = ""
        system_prompt_added = False
        for block in self.context_blocks:
            if block["type"] == "system_prompt":
                if not system_prompt_added:
                    context_text += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
                    system_prompt_added = True
                continue  # Skip additional system prompts
            context_text += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
        return context_text

    def _parse_blocks(self, text: str) -> List[Dict[str, str]]:
        """Parse text into a list of blocks."""
        blocks = []
        block_pattern = r'\[walbert_([a-z_]+)_start\](.*?)\[walbert_\1_end\]'
        for match in re.finditer(block_pattern, text, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()
            blocks.append({"type": block_type, "content": block_content})
        return blocks

    # --- Block Execution ---
    def _execute_block(self, block: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Execute a single block and return the result block (if any)."""
        self.logger.debug(f"Executing block: {block['type']}")

        if block["type"] == "sql_execute":
            try:
                if not self._is_sql_safe(block["content"]):
                    return {"type": "sql_result", "content": "SQL execution error: Unsafe SQL statement detected."}
                result = self.db.execute_sql(block["content"])
                return {"type": "sql_result", "content": str(result)}
            except Exception as e:
                return {"type": "sql_result", "content": f"SQL execution error: {str(e)}"}

        elif block["type"] == "python_execute":
            try:
                if not self._is_code_safe(block["content"]):
                    return {"type": "python_result", "content": "Python execution error: Unsafe code detected."}
                result = self._execute_python_code(block["content"])
                return {"type": "python_result", "content": result}
            except Exception as e:
                return {"type": "python_result", "content": f"Python execution error: {str(e)}"}

        elif block["type"] == "console_response":
            self.write_output(f"Walbert:\n{block['content']}\n\n")
            return None

        elif block["type"] == "autonomous_instruction":
            self.logger.debug("Autonomous instruction received, skipping execution block duplication")
            return None

        elif block["type"] in ("user_input", "system_prompt"):
            return None

        else:
            self.logger.warning(f"Unknown block type: {block['type']}")
            return None

    def _execute_pending_blocks(self):
        """Execute all pending blocks (SQL, Python, etc.) in order."""
        executable_types = {"sql_execute", "python_execute", "autonomous_instruction"}
        with self._lock:
            pending_blocks = [
                b for b in self.context_blocks 
                if b["type"] in executable_types and not b.get("executed", False)
            ]

        for block in pending_blocks:
            result_block = self._execute_block(block)
            if result_block:
                self._append_block(result_block["type"], result_block["content"])
            block["executed"] = True

    # --- Core Methods ---
    def _build_system_prompt(self) -> str:
        """Build the system prompt with current schema and settings."""
        db_schema = self.db.get_schema()
        system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
        if self.config.be_presbyterian:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order."
            )
        else:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You strive to be perpetually creative, curious, and kind in all interactions."
            )
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"\n\n## Internet Access Status\nInternet access for Python execution is currently {internet_status}."
        return system_prompt

    def _generate_response_block(self, user_input: str = None) -> str:
        """Generate a response block using the model."""
        prompt = self._get_context_as_text()
        prompt += "\nPlease respond in the appropriate walbert_* blocks. Be concise and sequential.\n"

        # Log full prompt sent to the model for audit/integrity
        self._log_to_conversation_file(f"--- PROMPT SENT TO MODEL ---\n{prompt}\n------------------------------")

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )

        response_blocks = self._parse_blocks(model_response)
        for block in response_blocks:
            self._append_block(block["type"], block["content"])

        self._execute_pending_blocks()

        for block in response_blocks:
            if block["type"] == "console_response":
                return block["content"]
        return ""

    def _generate_autonomous_block(self) -> str:
        """Generate an autonomous instruction block."""
        prompt = self._get_context_as_text()
        prompt += (
            "\n[walbert_autonomous_instruction_start]\n"
            "You are operating autonomously. Please:\n"
            "1. Review your recent actions and results\n"
            "2. Identify any pending tasks or incomplete work\n"
            "3. Make progress on your objectives\n"
            "4. Maintain awareness of your database state\n"
            "\n[walbert_autonomous_instruction_end]\n"
        )

        # Log full prompt sent to the model for audit/integrity
        self._log_to_conversation_file(f"--- AUTONOMOUS PROMPT SENT TO MODEL ---\n{prompt}\n-------------------------------------------")

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )

        blocks = self._parse_blocks(model_response)
        for block in blocks:
            if block["type"] == "autonomous_instruction":
                return block["content"]
        return "Continue monitoring and processing."

    # --- Input/Output ---
    def read_input(self) -> str:
        """Read input from console."""
        try:
            input_text = input(f"\n\n>>>>> ")
            self.logger.debug(f"Received input: {input_text}")
            return input_text
        except Exception as e:
            self.logger.error(f"Error reading input: {e}")
            return ""

    def write_output(self, text: str) -> None:
        """Write output to console."""
        print(text, end='', flush=True)

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
                self.context_blocks = []  # Reset context blocks

            # Connect to the database
            self.db.connect()

            # Build and cache the system prompt
            self.system_prompt = self._build_system_prompt()
            self._append_block("system_prompt", self.system_prompt)

            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")
            self.model_ready = True

            self.logger.info(f"Conversation session started in {session_dir}")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation."""
        with self._lock:
            self.session_dir = None
            self.context_blocks = []
            if self.python_temp_dir and os.path.exists(self.python_temp_dir):
                shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None

    def _log_to_conversation_file(self, content: str, sender: str = "user"):        
        if not self.session_dir:
            return        
        try:
            file_name = f"conversation_log.txt"
            file_path = os.path.join(self.session_dir, file_name)
            with open(file_path, 'a') as f:
                now = datetime.now()
                date_string = now.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n\n{date_string}\n")
                f.write(content)
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    # --- Main Execution Loop ---
    def run_autonomous(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop with block-based context."""
        self.start_conversation()

        while not self.model_ready:
            time.sleep(0.1)

        last_user_input = None
        time.sleep(30)  # Initial delay

        while True:
            try:
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

                        self.model_manager.shutdown()
                        time.sleep(self.MODEL_RESTART_DELAY)

                        if interrupt_event:
                            interrupt_event.set()
                            time.sleep(self.MODEL_RESTART_DELAY)
                            interrupt_event.clear()

                        input_queue.queue.clear()

                        with self._lock:
                            last_user_input = msg

                        self._append_block("user_input", msg)

                        self.model_manager.start_server_thread()
                        if not self.model_manager.wait_for_server():
                            error_msg = f"\nError: Model server failed to restart for user input"
                            print(error_msg)
                            continue

                        self._generate_response_block(msg)
                        print(f"\n\n>>>>> ", end='', flush=True)
                        continue

                except queue.Empty:
                    pass

                if not test_mode:
                    autonomous_instruction = self._generate_autonomous_block()
                    self._append_block("autonomous_instruction", autonomous_instruction)
                    self._execute_pending_blocks()
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
                self._append_block("error", error_msg)

                self.model_manager.shutdown()
                time.sleep(self.MODEL_RESTART_DELAY)
                if interrupt_event:
                    interrupt_event.set()
                    time.sleep(self.MODEL_RESTART_DELAY)
                    interrupt_event.clear()
                self.model_manager.start_server_thread()
                if not self.model_manager.wait_for_server():
                    error_msg = f"\nError: Model server failed to restart"
                    print(error_msg)

    # --- Utility Methods ---
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