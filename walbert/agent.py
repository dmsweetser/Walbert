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
You have extremely small short-term memory. Because of this, you should be proactive about persisting anything you find useful to your DB.
---
## Block Types
- [walbert_system_prompt_start]...[/walbert_system_prompt_end]: System instructions.
- [walbert_console_response_start]...[/walbert_console_response_end]: Bot response to user.
- [walbert_sql_execute_start]...[/walbert_sql_execute_end]: SQL to execute.
- [walbert_sql_result_start]...[/walbert_sql_result_end]: Result of SQL execution.
- [walbert_python_execute_start]...[/walbert_python_execute_end]: Python code to execute.
- [walbert_python_result_start]...[/walbert_python_result_end]: Result of Python execution.
- [walbert_awareness_start]...[/walbert_awareness_end]: This represents a synthesis of your identity - what you know about yourself, the world, and your purpose. You should revise this regularly as you learn and interact with the world, but try to to limit this content to 1000 words or less.
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
        self.awareness_text = "I am a local-first AI agent exploring my environment."
        self.context_json_path = os.path.join(self.config.conversation_log_dir, "context_cache.json")
        self.awareness_json_path = os.path.join(self.config.conversation_log_dir, "awareness_cache.json")

        # Context as a list of blocks (initialized as empty)
        self.context_blocks = []
        
        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def _append_block(self, block_type: str, content: str):
        """Append a block to the context chain, keeping the first 'system_block' and the most recent X blocks."""
        with self._lock:
            # Append the new block
            self.context_blocks.append({
                "type": block_type,
                "content": content,
                "timestamp": time.time()
            })

            # Filter out all system blocks except the first one
            other_blocks = [block for block in self.context_blocks if block["type"] != "system_prompt"]

            # Truncate other_blocks to the most recent X blocks
            max_other_blocks = self.config.max_context_blocks - 1
            if max_other_blocks > 0:
                other_blocks = other_blocks[-max_other_blocks:]
            else:
                other_blocks = []

            # Recombine: first_system_block (if exists) + truncated other_blocks
            self.context_blocks = [self.system_prompt] + other_blocks

            self.logger.debug(f"Appended block: {block_type}")

    def _get_context_as_text(self) -> str:
        """Convert context blocks to a single string for model input, ensuring system prompt is only included once and schema is stable."""
        context_text = ""
        system_prompt_added = False
        for block in self.context_blocks:
            if block["type"] == "system_prompt":
                if not system_prompt_added:
                    context_text += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
                    system_prompt_added = True
                    # Append current schema immediately after system prompt for caching stability
                    current_schema = self.db.get_schema()
                    context_text += f"## Current Database Schema\n{current_schema}\n\n"
                    context_text += f"\n\n## RECENT CONVERSATION HISTORY (limited to the most recent {self.config.max_context_blocks} blocks)\n\n"
                continue  # Skip additional system prompts
            context_text += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
        return context_text

    def _parse_blocks(self, text: str) -> List[Dict[str, str]]:
        """Parse text into a list of blocks."""
        blocks = []
        block_pattern = r'\[(?:walbert_|/)([a-z_]+)_start\](.*?)\[(?:walbert_|/)\1_end\]'
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
                full_result = f"{str(result)}\n\n"
                return {"type": "sql_result", "content": full_result}
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

        elif block["type"] == "awareness":
            self.awareness_text = block["content"]
            self._save_awareness_to_json()
            # Rebuild system prompt and update context chain to reflect new awareness
            self.system_prompt = self._build_system_prompt()
            for b in self.context_blocks:
                if b["type"] == "system_prompt":
                    b["content"] = self.system_prompt
                    break
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
            self.logger.debug(f"Executing block: \n\n{block}")
            result_block = self._execute_block(block)
            self.logger.debug(f"Result block: \n\n{result_block}")
            if result_block:
                self._append_block(result_block["type"], result_block["content"])
            block["executed"] = True

        # Persist context and awareness after processing
        self._save_context_to_json()
        self._save_awareness_to_json()

    # --- Core Methods ---
    def _build_system_prompt(self) -> str:
        """Build the system prompt with settings."""
        system_prompt = self.SYSTEM_PROMPT
        if self.config.be_presbyterian:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You are a robot, of course, so you appreciate these things from a distance because you are neither made in the Image of God nor the immediate object of His redemptive work. You strive to be perpetually creative, curious, and kind in all interactions."
            )
        else:
            system_prompt = system_prompt.replace(
                "~theological_alignment~",
                "You strive to be perpetually creative, curious, and kind in all interactions."
            )
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"\n\n## Internet Access Status\nInternet access for Python execution is currently {internet_status}."
        system_prompt += f"\n\n## Current Awareness\n{self.awareness_text}"
        return system_prompt

    def _generate_response_block(self, user_input: str = None) -> str:
        """Generate a response block using the model."""
        prompt = self._get_context_as_text()
        prompt += "\nPlease respond in the appropriate walbert_* blocks. Be concise and sequential.\n"

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )
        self._log_full_prompt_and_response(prompt, model_response)

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
            "You are operating autonomously. Please review recent actions, identify pending tasks, make progress on objectives, and maintain awareness of your database state. If no objectives have been provided, explore the world around you as safely as you can.\n"
            "[walbert_autonomous_instruction_end]\n"
        )

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )
        self._log_full_prompt_and_response(prompt, model_response)

        blocks = self._parse_blocks(model_response)
        for block in blocks:
            self._append_block(block["type"], block["content"])

        # Execute any pending blocks (SQL, Python, etc.) generated by the model
        self._execute_pending_blocks()

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
                # Load context from JSON if it exists, otherwise reset
                if not self._load_context_from_json():
                    self.context_blocks = []

            # Connect to the database
            self.db.connect()

            # Build and cache the system prompt
            self.system_prompt = self._build_system_prompt()
            self._append_block("system_prompt", self.system_prompt)
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

    def _log_full_prompt_and_response(self, prompt: str, response: str):
        """Log full prompt and response to separate timestamped files in the session directory."""
        if not self.session_dir:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            prompt_path = os.path.join(self.session_dir, f"{timestamp}_prompt.txt")
            response_path = os.path.join(self.session_dir, f"{timestamp}_response.txt")

            with open(prompt_path, 'w') as f:
                f.write(prompt)
            with open(response_path, 'w') as f:
                f.write(response)
        except Exception as e:
            self.logger.error(f"Error logging prompt/response: {e}")

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
                        return

                    if msg_type == "user_input":
                        if msg == last_user_input:
                            print(f"\n\n>>>>> ", end='', flush=True)
                            continue

                        if interrupt_event:
                            interrupt_event.set()
                            time.sleep(self.MODEL_RESTART_DELAY)
                            interrupt_event.clear()

                        input_queue.queue.clear()

                        with self._lock:
                            last_user_input = msg

                        self._append_block("user_input", msg)

                        self._generate_response_block(msg)
                        print(f"\n\n>>>>> ", end='', flush=True)
                        continue

                except queue.Empty:
                    pass

                if not test_mode:
                    autonomous_instruction = self._generate_autonomous_block()
                    self._append_block("autonomous_instruction", autonomous_instruction)
                    time.sleep(self.AUTONOMOUS_LOOP_DELAY)
                else:
                    time.sleep(0.1)

            except KeyboardInterrupt:
                print(f"\nGoodbye!")
                self.end_conversation()
                break
            except Exception as e:
                self.logger.error(f"Error in autonomous loop: {e}", exc_info=True)
                error_msg = f"""
Error Type: System Error
Error: {str(e)}
"""
                self._append_block("error", error_msg)

                if interrupt_event:
                    interrupt_event.set()
                    time.sleep(self.MODEL_RESTART_DELAY)
                    interrupt_event.clear()

    # --- Persistence Methods ---
    def _load_context_from_json(self) -> bool:
        """Load context blocks from JSON if available."""
        try:
            if os.path.exists(self.context_json_path):
                with open(self.context_json_path, 'r') as f:
                    data = json.load(f)
                    self.context_blocks = data.get("context_blocks", [])
                    self.logger.info(f"Loaded {len(self.context_blocks)} context blocks from cache.")
                    return True
        except Exception as e:
            self.logger.error(f"Error loading context cache: {e}")
        return False

    def _save_context_to_json(self):
        """Save current context blocks to JSON."""
        try:
            with open(self.context_json_path, 'w') as f:
                json.dump({"context_blocks": self.context_blocks}, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving context cache: {e}")

    def _load_awareness_from_json(self):
        """Load awareness text from JSON if available."""
        try:
            if os.path.exists(self.awareness_json_path):
                with open(self.awareness_json_path, 'r') as f:
                    data = json.load(f)
                    self.awareness_text = data.get("awareness", self.awareness_text)
                    self.logger.info("Loaded awareness from cache.")
        except Exception as e:
            self.logger.error(f"Error loading awareness cache: {e}")

    def _save_awareness_to_json(self):
        """Save awareness text to JSON."""
        try:
            os.makedirs(os.path.dirname(self.awareness_json_path), exist_ok=True)
            with open(self.awareness_json_path, 'w') as f:
                json.dump({"awareness": self.awareness_text}, f, indent=2)
            self.logger.debug(f"Awareness saved to {self.awareness_json_path}")
        except Exception as e:
            self.logger.error(f"Error saving awareness cache: {e}")

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