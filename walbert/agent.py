#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import select
import sys
import os
import logging
import json
import threading
import time
import queue
import shutil
import datetime
from walbert.config import Config
from walbert.model_config import ModelConfig
from walbert.state import AgentState
from walbert.parser import BlockParser
from walbert.executor import BlockExecutor

# Initialize logging
os.makedirs('instance', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instance/walbert.log')
    ]
)
logger = logging.getLogger('walbert')


def load_config() -> Config:
    """Load system configuration"""
    try:
        with open('instance/config.json', 'r') as f:
            config_data = json.load(f)
            model_configs = {
                'model': ModelConfig(
                    model_path=config_data['model_configs']['model']['model_path'],
                    context_size=config_data['model_configs']['model']['context_size'],
                    output_tokens=config_data['model_configs']['model']['output_tokens'],
                    temperature=config_data['model_configs']['model']['temperature'],
                    top_p=config_data['model_configs']['model']['top_p'],
                    top_k=config_data['model_configs']['model']['top_k'],
                    min_p=config_data['model_configs']['model']['min_p']
                )
            }
            return Config(
                model_configs=model_configs,
                llama_binary_path=config_data['llama_binary_path'],
                mmproj_path=config_data.get('mmproj_path', ""),
                log_level=config_data.get('log_level', "INFO"),
                be_presbyterian=bool(config_data.get('be_presbyterian', True)),
                max_context_blocks=config_data['max_context_blocks']
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)


class WalbertAgent:
    """Refactored Walbert agent with separated responsibilities."""

    DEFAULT_USER_CONTROL_TIMEOUT = 300
    MODEL_RESTART_DELAY = 5
    AUTONOMOUS_LOOP_DELAY = 10

    def __init__(self, config, model_manager=None):
        self.config = config
        self.model_manager = model_manager
        self.state = AgentState(config, None)
        self.executor = None
        self.parser = BlockParser()
        self.internet_access = False
        self._lock = threading.Lock()
        self.input_timeout = self.config.autonomous_operation_timeout
        self.last_input_time = 0
        self.model_ready = False
        self.processing_cycle = 0
        self.current_conversation_file = None
        self.db = None
        self.print_raw = False

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def _init_components(self):
        """Initialize components that depend on DB connection."""
        from walbert.database.manager import DatabaseManager
        from walbert.models.manager import ModelManager
        if self.model_manager is None:
            self.model_manager = ModelManager(self.config)
        self.db = DatabaseManager(self.config.database_path)
        self.state.db = self.db
        self.executor = BlockExecutor(self.config, self.db, self.internet_access)

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
                self._init_components()
                self.db.connect()
                self.state.refresh_system_prompt()
                self.model_ready = True

            self.logger.info(f"Conversation session started in {session_dir}")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation."""
        with self._lock:
            self.session_dir = None
            if self.db and hasattr(self.db, 'close'):
                self.db.close()
            if self.executor and self.executor.python_temp_dir and os.path.exists(self.executor.python_temp_dir):
                shutil.rmtree(self.executor.python_temp_dir)
                self.executor.python_temp_dir = None

    def _generate_response_block(self, user_input: str = None) -> str:
        """Generate a response block using the model."""
        prompt = self.state.get_prompt(self.internet_access, max_tokens=self.config.model_configs['model'].context_size)
        prompt += "\nPlease respond in the appropriate walbert_* blocks. Be concise and sequential.\n"

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )
        self._log_full_prompt_and_response(prompt, model_response)

        response_blocks = self.parser.parse(model_response)
        self._execute_pending_blocks(response_blocks)

        for block in response_blocks:
            if block["type"] == "console_response":
                return block["content"]
        return ""

    def _generate_autonomous_block(self) -> str:
        """Generate an autonomous instruction block."""
        prompt = self.state.get_prompt(self.internet_access, max_tokens=self.config.model_configs['model'].context_size)
        prompt += (
            "\nYou are operating autonomously. Please review recent actions, identify pending tasks, make progress on objectives, and maintain awareness of your database state. If no objectives have been provided, explore the world around you as safely as you can.\n"
        )

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            None
        )
        self._log_full_prompt_and_response(prompt, model_response)

        blocks = self.parser.parse(model_response)

        self._execute_pending_blocks(blocks)
        return "Continue monitoring and processing."

    def _execute_pending_blocks(self, provided_blocks):
        """Execute all pending blocks (SQL, Python, etc.) in order."""
        executable_types = {"sql_execute", "python_execute", "awareness"}
        with self._lock:
            pending_blocks = [
                b for b in provided_blocks
                if b["type"] in executable_types
            ]

        for block in pending_blocks:
            self.logger.debug(f"Executing block: {block}")
            result_block = self.executor.execute(block)
            if result_block:
                if result_block["type"] == "awareness_update":
                    self.state.update_awareness(result_block["content"])
                else:
                    self.state.append_block(block["type"], block["content"])
                    self.state.append_block(result_block["type"], block["content"])
                    self.write_output(json.dumps(result_block, indent=2), result_block["type"])
                        
            block["executed"] = True
        
        # Ensure state syncs immediately after execution so next prompt reflects changes
        self.state._sync_state()

    def _log_full_prompt_and_response(self, prompt: str, response: str):
        """Log full prompt and response to separate timestamped files in the session directory."""
        if not hasattr(self, 'session_dir') or not self.session_dir:
            return
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            prompt_path = os.path.join(self.session_dir, f"{timestamp}_prompt.txt")
            response_path = os.path.join(self.session_dir, f"{timestamp}_response.txt")

            with open(prompt_path, 'w') as f:
                f.write(prompt)
            with open(response_path, 'w') as f:
                f.write(response)
        except Exception as e:
            self.logger.error(f"Error logging prompt/response: {e}")

    def write_output(self, text: str, block_type: str = None) -> None:
        """Write output to console."""
        if block_type == "console_response" or self.print_raw:
            print(text, end='', flush=True)

    def run_autonomous(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop with block-based context."""
        self.start_conversation()

        while not self.model_ready:
            time.sleep(0.1)

        last_user_input = None
        time.sleep(30)

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

                        self.state.append_block("user_input", msg)
                        self._generate_response_block(msg)
                        print(f"\n\n>>>>> ", end='', flush=True)
                        continue

                except queue.Empty:
                    pass

                if not test_mode:
                    self._generate_autonomous_block()
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
                self.state.append_block("error", error_msg)

                if interrupt_event:
                    interrupt_event.set()
                    time.sleep(self.MODEL_RESTART_DELAY)
                    interrupt_event.clear()

    def shutdown(self):
        """Shutdown agent cleanly."""
        self.end_conversation()
