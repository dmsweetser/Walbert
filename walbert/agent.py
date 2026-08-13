#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import select
import subprocess
import sys
import os
import logging
import json
import threading
import time
import queue
import shutil
import datetime
from typing import Dict, Any, Optional
from walbert.config import Config
from walbert.model_config import ModelConfig
from walbert.state import AgentState
from walbert.parser import BlockParser
from walbert.executor import BlockExecutor
from walbert.comms import NetworkManager
from walbert.audio_thread import AudioIOThread

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
                be_presbyterian=bool(config_data.get('be_presbyterian', True))
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

    def __init__(self, config, model_manager=None, input_queue=None):
        self.config = config
        self.model_manager = model_manager
        self.state = AgentState(config)
        self.executor = None
        self.parser = BlockParser()
        self._lock = threading.Lock()
        self.input_timeout = self.config.autonomous_operation_timeout
        self.last_input_time = 0
        self.model_ready = False
        self.processing_cycle = 0
        self.current_conversation_file = None
        self.python_execution_enabled = config.python_execution_enabled
        self.bash_execution_enabled = config.bash_execution_enabled
        self.print_raw = False
        self.waiting_for_user = False
        self.input_queue = input_queue
        self.comms = NetworkManager(config)
        self.audio_thread = None
        self._pending_peer_ip = None
        self._comms_started = False
        self._audio_started = False

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def _init_components(self):
        """Initialize components that depend on runtime state."""
        from walbert.models.manager import ModelManager
        if self.model_manager is None:
            self.model_manager = ModelManager(self.config)
        self.executor = BlockExecutor(self.config)

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
                self.state.refresh_system_prompt()
                self.model_ready = True
                if self.config.peer_communication_enabled:
                    self.comms.start()
                else:
                    self.comms = None

            self.logger.info(f"Conversation session started in {session_dir}")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation."""
        with self._lock:
            self.session_dir = None
            if self.executor and self.executor.python_temp_dir and os.path.exists(self.executor.python_temp_dir):
                shutil.rmtree(self.executor.python_temp_dir)
                self.executor.python_temp_dir = None
            self.comms.stop()

    def _generate_response_block(self, user_input, interrupt_event) -> str:
        """Generate a response block using the model."""
        prompt = self.state.get_prompt(max_tokens=self.config.model_configs['model'].context_size, user_input=user_input)
        prompt += f"{chr(10)}Please respond in the appropriate walbert_* blocks. Be concise and sequential.\n"
        # Inject peer list into prompt context
        peers = self.comms.get_peer_list()
        if peers:
            prompt += f"\n## Active Peers\n{', '.join(peers)}\n"

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            interrupt_event
        )

        print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
        self._log_full_prompt_and_response(prompt, model_response)

        # Abort if interrupted before processing blocks
        if interrupt_event and interrupt_event.is_set():
            interrupt_event.clear()
            return ""
            
        response_blocks = self.parser.parse(model_response)
        self._execute_pending_blocks(response_blocks)

        console_content = ""
        is_blocking = False
        for block in response_blocks:
            if block["type"] in ("console_response_blocking", "console_response_nonblocking"):
                console_content = block["content"]
                is_blocking = block["type"] == "console_response_blocking"
                break
        
        if console_content:
            self.write_output(console_content, "console_response")
            if is_blocking:
                print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                self.waiting_for_user = True
                # Timeout logic handled in run_autonomous
            else:
                print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                self.waiting_for_user = False
        else:
            self.waiting_for_user = False
            
        return console_content

    def _generate_autonomous_block(self, interrupt_event) -> str:
        """Generate an autonomous instruction block."""
        prompt = self.state.get_prompt(max_tokens=self.config.model_configs['model'].context_size, user_input=None)
        prompt += (
            f"{chr(10)}You are operating autonomously. Please review your Current Ultimate Task, Current Immediate Task, and Current Impediment blocks. Synthesize your progress, update these tracking blocks as needed, and maintain awareness of your database state. If no objectives have been provided, explore the world around you as safely as you can.\n"
        )

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            interrupt_event
        )
        print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
        self._log_full_prompt_and_response(prompt, model_response)

        # Abort if interrupted before processing blocks
        if interrupt_event and interrupt_event.is_set():
            interrupt_event.clear()
            return "Continue monitoring and processing."
            
        blocks = self.parser.parse(model_response)

        self._execute_pending_blocks(blocks)

        console_content = ""
        for block in blocks:
            if block["type"] == "console_response":
                console_content = block["content"]
        
        if console_content:
            self.write_output(console_content, "console_response")
            print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            self.waiting_for_user = True
        else:
            self.waiting_for_user = False

        return "Continue monitoring and processing."

    def _execute_pending_blocks(self, provided_blocks):
        """Execute all pending blocks (SQL, Python, etc.) in order."""
        executable_types = {"python_execute", "bash_execute", "awareness", "ultimate_task", "immediate_task", "impediment", "peer_ip", "peer_message"}
        with self._lock:
            pending_blocks = [
                b for b in provided_blocks
                if b["type"] in executable_types
            ]

        for block in pending_blocks:
            self.logger.debug(f"Executing block: {block}")
            if block["type"] == "awareness":
                self.state.update_awareness(block["content"])
            elif block["type"] == "ultimate_task":
                self.state._ultimate_task = block["content"]
                self.state._save_ultimate_task()
            elif block["type"] == "immediate_task":
                self.state._immediate_task = block["content"]
                self.state._save_immediate_task()
            elif block["type"] == "impediment":
                self.state._impediment = block["content"]
                self.state._save_impediment()
            elif block["type"] == "peer_ip":
                self._pending_peer_ip = block["content"].strip()
            elif block["type"] == "peer_message":
                try:
                    if self.config.peer_communication_enabled and hasattr(self, '_pending_peer_ip') and self._pending_peer_ip:
                        self.comms.send_to_peer(self._pending_peer_ip, block["content"])
                        self.logger.info(f"Sent peer message to {self._pending_peer_ip}")
                        self._pending_peer_ip = None
                    else:
                        self.logger.warning("Peer communication disabled or IP not set.")
                except Exception as e:
                    self.logger.error(f"Failed to send peer message: {e}")
            elif block["type"] in ("python_execute", "bash_execute"):
                result_block = self.executor.execute(block)
                if result_block:
                    self.state.append_block(block["type"], block["content"])
                    self.state.append_block("execution_result", result_block["content"])
                    self.write_output(json.dumps(result_block, indent=2), result_block["type"])
                    print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                        
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
            if block_type in ("awareness", "context_blocks"):
                formatted_text = f"{chr(10)}".join(f"**** {line}" for line in text.split(f"{chr(10)}"))
                print(formatted_text, end='', flush=True)
            else:
                print(text, end='', flush=True)

    def run_autonomous(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop with block-based context."""
        self.start_conversation()

        while not self.model_ready:
            time.sleep(0.1)

        last_user_input = None

        while True:
            try:
                # Non-blocking check for user input
                try:
                    msg_type, msg = input_queue.get_nowait()
                except queue.Empty:
                    msg_type = None
                    msg = None

                if msg_type == "exit":
                    self.end_conversation()
                    return

                if msg_type == "user_input":
                    if msg == last_user_input:
                        print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                        continue
                    last_user_input = msg
                    self.state.append_block("user_input", msg)
                    self._generate_response_block(msg, interrupt_event)
                    print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                    continue

                if self.waiting_for_user:
                    try:
                        msg_type, msg = input_queue.get(timeout=self.config.user_input_timeout)
                        self.waiting_for_user = False
                        if msg_type == "exit":
                            self.end_conversation()
                            return
                        if msg_type == "user_input":
                            last_user_input = msg
                            self.state.append_block("user_input", msg)
                            self._generate_response_block(msg, interrupt_event)
                            print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
                            continue
                    except queue.Empty:
                        self.logger.info("User input timeout. Resuming autonomous operation.")
                        self.state.append_block("system_note", "User failed to respond within timeout. Continuing autonomous operation.")
                        self.waiting_for_user = False
                        continue
                else:
                    # Autonomous mode
                    # Check for incoming peer messages
                    pending_msgs = self.comms.get_pending_messages()
                    for msg in pending_msgs:
                        self.state.append_block("peer_message_received", json.dumps(msg))
                        self.logger.info(f"Processed peer message from {msg['peer_ip']}")
                    
                    if not test_mode:
                        self._generate_autonomous_block(interrupt_event)
                        time.sleep(self.AUTONOMOUS_LOOP_DELAY)
                    else:
                        time.sleep(0.1)

            except KeyboardInterrupt:
                print(f"{chr(10)}Goodbye!")
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

    def _install_python_package(self, package: str):
        """Install a Python package in the main environment."""
        print(f"{chr(10)}Installing package: {package}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"{chr(10)}Successfully installed {package}")
            print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {package}: {e.stderr}")
            print(f"{chr(10)}{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            self.logger.error(f"Failed to install package {package}: {e.stderr}")

    def shutdown(self):
        """Shutdown agent cleanly."""
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.stop()
        self.end_conversation()

    def enable_peer_communication(self):
        if not self.config.peer_communication_enabled:
            self.config.peer_communication_enabled = True
        if self._comms_started:
            return
        if self.comms is None:
            self.comms = NetworkManager(self.config)
        self.comms.start()
        self._comms_started = True
        self.logger.info(f"{chr(10)}Peer communication enabled{chr(10)}{chr(10)}")

    def disable_peer_communication(self):
        self.config.peer_communication_enabled = False
        if not self._comms_started:
            return
        if self.comms:
            self.comms.stop()
        self._comms_started = False
        self.logger.info(f"{chr(10)}Peer communication disabled{chr(10)}{chr(10)}")

    def enable_audio(self):
        self.config.audio_enabled = True
        self.config.stt_enabled = True
        self.config.tts_enabled = True
        if self._audio_started:
            return
        if not self.input_queue:
            import queue
            self.input_queue = queue.Queue()
        def on_response(text):
            if hasattr(self, 'audio_thread') and self.audio_thread:
                self.audio_thread.handle_console_response(text)
        self.audio_thread = AudioIOThread(self.input_queue, self.config, on_response)
        self.audio_thread.start()
        self._audio_started = True
        self.logger.info("Audio I/O thread enabled")

    def disable_audio(self):
        self.config.audio_enabled = False
        self.config.stt_enabled = False
        self.config.tts_enabled = False
        if not self._audio_started:
            return
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.stop()
            self.audio_thread.join(timeout=2)
            self.audio_thread = None
        self._audio_started = False
        self.logger.info("Audio I/O thread disabled")

    def send_peer_message(self, peer_ip: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a message to a specific peer and wait for response."""
        return self.comms.send_to_peer(peer_ip, message)
