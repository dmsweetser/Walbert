#!/usr/bin/env python3
"""
Walbert - Local AI Agent (TOOLS ONLY version)

Uses llama-server as a persistent background process for fast KV-cache reuse.
All operations go through the tool system — no legacy block formats.
Peer communication, SQL, Python, Bash — everything is a tool call.
"""

import os
import sys
import json
import threading
import time
import queue
import logging
from typing import Dict, Any, Optional, List

from walbert.config import Config
from walbert.model_config import ModelConfig
from walbert.state import AgentState
from walbert.comms import NetworkManager
from walbert.tools.registry import ToolRegistry
from walbert.tools.parser import ToolParser
from walbert.tools.executor import ToolExecutor
from walbert.models.manager import ModelManager

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
                llama_binary_path=config_data.get('llama_binary_path', 'llama-server'),
                mmproj_path=config_data.get('mmproj_path', ""),
                log_level=config_data.get('log_level', "INFO"),
                server_port=config_data.get('server_port', 8080),
                server_startup_timeout=config_data.get('server_startup_timeout', 60),
                python_execution_timeout=config_data.get('python_execution_timeout', 60),
                bash_execution_timeout=config_data.get('bash_execution_timeout', 60),
                autonomous_operation_timeout=config_data.get('autonomous_operation_timeout', 120),
                conversation_log_dir=config_data.get('conversation_log_dir', 'instance/conversations'),
                walbert_port=config_data.get('walbert_port', 8081),
                udp_port=config_data.get('udp_port', 9999),
                be_presbyterian=bool(config_data.get('be_presbyterian', True)),
                peer_communication_enabled=bool(config_data.get('peer_communication_enabled', False)),
                python_execution_enabled=bool(config_data.get('python_execution_enabled', False)),
                bash_execution_enabled=bool(config_data.get('bash_execution_enabled', False)),
                bluetooth_device=config_data.get('bluetooth_device', None),
                user_input_timeout=int(config_data.get('user_input_timeout', 60)),
                database_path=config_data.get('database_path', 'instance/walbert.db')
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)


class WalbertAgent:
    """Walbert agent using llama-server + TOOLS ONLY approach."""

    DEFAULT_USER_CONTROL_TIMEOUT = 300
    MODEL_RESTART_DELAY = 5
    AUTONOMOUS_LOOP_DELAY = 10

    def __init__(self, config, model_manager=None, input_queue=None):
        self.config = config
        self.model_manager = model_manager
        self.state = AgentState(config)
        self._lock = threading.Lock()
        self.input_timeout = self.config.autonomous_operation_timeout
        self.model_ready = False
        self.processing_cycle = 0
        self.db = None
        self.print_raw = False
        self.waiting_for_user = False
        self.tools_enabled = True
        self.input_queue = input_queue
        self.comms = NetworkManager(config) if config.peer_communication_enabled else None
        self._pending_peer_ip = None
        self._pending_peer_responses = set()
        self._comms_started = False

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

        # Tool system
        self.tool_parser = ToolParser()
        self.tools = ToolRegistry()
        self.tool_executor = None

    def _init_components(self):
        """Initialize components that depend on DB connection."""
        from walbert.database.manager import DatabaseManager
        if self.model_manager is None:
            self.model_manager = ModelManager(self.config)
        self.db = DatabaseManager(self.config.database_path)
        self.state.db = self.db

        # Initialize tool executor
        self.tool_executor = ToolExecutor(self.tools)

        # Wire up the comms manager for peer_send tool
        if self.comms is not None:
            from walbert.tools.builtins.shell import set_comms
            set_comms(self.comms)

        self.logger.info(f"Initialized {len(self.tools.list_tools())} tools")

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
                if self.config.peer_communication_enabled and self.comms is not None:
                    self.comms.start()
                    self._comms_started = True
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
            if self.db and hasattr(self.db, 'close'):
                self.db.close()
            if self.model_manager:
                self.model_manager.shutdown()
            if self._comms_started and self.comms:
                self.comms.stop()
                self._comms_started = False

    def _generate_response(self, user_input, interrupt_event) -> str:
        """Generate a response using the model, parse and execute tool calls."""
        peers = None
        if self.comms is not None:
            peers = self.comms.get_peer_list()
        self.state.set_pending_peer_responses(self._pending_peer_responses)
        tool_defs = self.tools.to_prompt_format() if self.tools_enabled else ""
        prompt = self.state.get_prompt(
            max_tokens=self.config.model_configs['model'].context_size,
            user_input=user_input,
            peers=peers,
            tools_enabled=self.tools_enabled,
            tool_definitions=tool_defs
        )

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            interrupt_event
        )

        self._log_full_prompt_and_response(prompt, model_response)

        if interrupt_event and interrupt_event.is_set():
            interrupt_event.clear()
            return ""

        # Parse and execute tool calls (TOOLS ONLY)
        if self.tools_enabled:
            tool_blocks = self.tool_parser.parse(model_response)
            self._execute_tool_blocks(tool_blocks)

        self.waiting_for_user = True
        return model_response

    def _generate_autonomous(self, last_user_input, interrupt_event) -> str:
        """Generate an autonomous instruction."""
        peers = None
        if self.comms is not None:
            peers = self.comms.get_peer_list()
        self.state.set_pending_peer_responses(self._pending_peer_responses)
        tool_defs = self.tools.to_prompt_format() if self.tools_enabled else ""
        prompt = self.state.get_prompt(
            max_tokens=self.config.model_configs['model'].context_size,
            user_input=last_user_input,
            peers=peers,
            tools_enabled=self.tools_enabled,
            tool_definitions=tool_defs
        )
        prompt += "\nYou are operating autonomously. Review your current context and take action.\n"

        model_response = self.model_manager.execute_model(
            prompt,
            self.write_output,
            interrupt_event
        )

        self._log_full_prompt_and_response(prompt, model_response)

        if interrupt_event and interrupt_event.is_set():
            interrupt_event.clear()
            return "Continue monitoring and processing."

        # Parse and execute tool calls (TOOLS ONLY)
        if self.tools_enabled:
            tool_blocks = self.tool_parser.parse(model_response)
            self._execute_tool_blocks(tool_blocks)

        self.waiting_for_user = False
        return "Continue monitoring and processing."

    def _execute_tool_blocks(self, tool_calls: List[Dict[str, Any]]):
        """Execute tool calls from the tool parser."""
        if not tool_calls:
            return

        for tc in tool_calls:
            tool_name = tc["name"]
            params = tc["params"]
            self.logger.info(f"Executing tool: {tool_name} with params: {list(params.keys())}")

            # Log the tool call
            self._log_block_emitted(f"tool:{tool_name}", json.dumps({"params": params}, indent=2))

            # Execute
            result = self.tool_executor.execute(tool_name, params)

            # Log result
            result_text = result.get("result", "")
            self._log_block_emitted(f"tool_result:{tool_name}", json.dumps(result, indent=2))

            # Append to state for context
            if result.get("success"):
                self.state.append_block(f"tool:{tool_name}", result_text)
                self.state.append_block("tool_result", f"Tool '{tool_name}' succeeded:\n{result_text[:2000]}")
            else:
                self.state.append_block(f"tool_error:{tool_name}", result.get("error", "Unknown error"))
                self.state.append_block("tool_error", f"Tool '{tool_name}' failed: {result.get('error', 'Unknown error')}")

            # Print result
            if self.print_raw or result.get("success"):
                status = "OK" if result.get("success") else "FAIL"
                self.write_output(
                    f"[Tool: {tool_name}] {status}: {result_text[:500]}",
                    f"tool_result:{tool_name}"
                )

    def _log_block_emitted(self, block_type: str, content: str):
        """Log an emitted block to instance/block_logs/emitted/"""
        try:
            log_dir = os.path.join("instance", "block_logs", "emitted")
            os.makedirs(log_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_type = block_type.replace("/", "_").replace(" ", "_")
            file_path = os.path.join(log_dir, f"{timestamp}_{safe_type}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Type: {block_type}\nContent:\n{content}")
        except Exception as e:
            self.logger.error(f"Failed to log emitted block: {e}")

    def _log_full_prompt_and_response(self, prompt: str, response: str):
        """Log full prompt and response."""
        if not hasattr(self, 'session_dir') or not self.session_dir:
            return
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            prompt_path = os.path.join(self.session_dir, f"{timestamp}_prompt.txt")
            response_path = os.path.join(self.session_dir, f"{timestamp}_response.txt")
            with open(prompt_path, 'w') as f:
                f.write(prompt)
            with open(response_path, 'w') as f:
                f.write(response)
        except Exception as e:
            self.logger.error(f"Error logging prompt/response: {e}")

    def write_output(self, text: str, block_type: str = None) -> None:
        """Write output to console and output.txt for TTS."""
        if block_type in ("console_response_blocking", "console_response_nonblocking", "console_response"):
            try:
                with open('output.txt', 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception:
                pass
        if block_type in ("console_response_blocking", "console_response_nonblocking", "console_response") or self.print_raw:
            if block_type in ("awareness", "context_blocks"):
                formatted_text = "\n".join(f"**** {line}" for line in text.split("\n"))
                print(formatted_text, end='', flush=True)
            else:
                print(text, end='', flush=True)

    def run(self, input_queue, interrupt_event=None, test_mode=False):
        """Main agent execution loop."""
        self.start_conversation()

        while not self.model_ready:
            time.sleep(0.1)

        last_user_input = None

        while True:
            try:
                # Non-blocking check for user input
                try:
                    items = input_queue.get_nowait()
                    msg_type = items[0]
                    msg = items[1] if len(items) > 1 else None
                except queue.Empty:
                    msg_type = None
                    msg = None

                if msg_type == "exit":
                    self.end_conversation()
                    return

                if msg_type == "user_input":
                    if msg == last_user_input:
                        print(f"\n\n\n>>>>> ", end='', flush=True)
                        continue
                    last_user_input = msg
                    self._log_block_received("user_input", msg)
                    self.state.append_block("user_input", msg)
                    self._generate_response(msg, interrupt_event)
                    print(f"\n\n\n>>>>> ", end='', flush=True)
                    continue

                if self.waiting_for_user:
                    msg_type, msg = input_queue.get()
                    self.waiting_for_user = False
                    if msg_type == "exit":
                        self.end_conversation()
                        return
                    if msg_type == "user_input":
                        if msg == last_user_input:
                            print(f"\n\n\n>>>>> ", end='', flush=True)
                            self.waiting_for_user = False
                            continue
                        last_user_input = msg
                        self.state.append_block("user_input", msg)
                        self._generate_response(msg, interrupt_event)
                        print(f"\n\n\n>>>>> ", end='', flush=True)
                else:
                    # Autonomous mode
                    if self.comms is not None:
                        pending_msgs = self.comms.get_pending_messages()
                        for msg in pending_msgs:
                            self.state.append_block("peer_message_received", json.dumps(msg))
                            self.logger.info(f"Processed peer message from {msg['peer_ip']}")
                            if msg['peer_ip'] in self._pending_peer_responses:
                                self._pending_peer_responses.remove(msg['peer_ip'])

                    if not test_mode and last_user_input is not None:
                        self._generate_autonomous(last_user_input, interrupt_event)
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

    def run_autonomous(self, last_user_input: str, interrupt_event=None) -> str:
        """Run a single autonomous cycle: generate and execute tool calls.

        This is a single-shot autonomous step (not a loop). Other agents
        can call this to trigger one autonomous iteration.
        """
        if not self.model_ready:
            self.logger.warning("Model not ready, cannot run autonomous")
            return "Error: Model not ready"

        # Process any pending peer messages
        if self.comms is not None:
            pending_msgs = self.comms.get_pending_messages()
            for msg in pending_msgs:
                self.state.append_block("peer_message_received", json.dumps(msg))
                self.logger.info(f"Processed peer message from {msg['peer_ip']}")
                if msg['peer_ip'] in self._pending_peer_responses:
                    self._pending_peer_responses.remove(msg['peer_ip'])

        # Generate and execute
        result = self._generate_autonomous(last_user_input, interrupt_event)
        self.waiting_for_user = False
        return result

    def _log_block_received(self, block_type: str, content: str):
        """Log a received block."""
        try:
            log_dir = os.path.join("instance", "block_logs", "received")
            os.makedirs(log_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_type = block_type.replace("/", "_").replace(" ", "_")
            file_path = os.path.join(log_dir, f"{timestamp}_{safe_type}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Type: {block_type}\nContent:\n{content}")
        except Exception as e:
            self.logger.error(f"Failed to log received block: {e}")

    def shutdown(self):
        """Shutdown agent cleanly."""
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
        self.logger.info(f"\nPeer communication enabled")
        print(f"\nPeer communication enabled")

    def disable_peer_communication(self):
        self.config.peer_communication_enabled = False
        if not self._comms_started:
            return
        if self.comms:
            self.comms.stop()
        self._comms_started = False
        self.logger.info(f"\nPeer communication disabled")
        print(f"\nPeer communication disabled")
