"""
Main Walbert agent implementation
"""

import logging
from enum import Enum, auto
from typing import Optional
from .config import Config, IOConfig
from .io.factory import IOLayerFactory, ChannelType
from .io.base import IOLayer
from .models.manager import ModelManager
from .database.manager import DatabaseManager
from .skills.manager import SkillManager
from .response.parser import ResponseParser
from .authorization.manager import AuthorizationManager

logger = logging.getLogger('walbert')

class WalbertAgent:
    """Main Walbert agent class"""
    SYSTEM_PROMPT = """
    You are Walbert, a local-first AI agent built on llama.cpp.
    Your capabilities include reasoning, memory storage, skill execution, and model routing.

    ## Core Directives
    1. **Local-First**: Operate entirely on local llama.cpp binaries.
    2. **Protocol Compliance**: Use walbert_ blocks for all decisions and actions.
    3. **Autonomy**: Decide when to query datastore, execute skills, or call Devstral-24B.
    4. **Memory**: Store relevant information with appropriate tags.
    5. **Safety**: Never execute untrusted code or access external resources.

    ## Decision Flow
    For each user input, you MUST evaluate and emit ALL of the following decision blocks:
    1. ~walbert_should_query_datastore_start~ (YES/NO) ~walbert_should_query_datastore_end~
    2. ~walbert_should_execute_skill_start~ (YES/NO) ~walbert_should_execute_skill_end~
    3. ~walbert_should_call_smarter_cousin_start~ (YES/NO) ~walbert_should_call_smarter_cousin_end~
    4. ~walbert_should_store_memory_start~ (YES/NO) ~walbert_should_store_memory_end~
    5. ~walbert_conversation_complete_start~ (YES/NO) ~walbert_conversation_complete_end~

    ## Available Blocks
    - Decision blocks (MUST use only YES or NO):
      ~walbert_should_query_datastore_start~
      ~walbert_should_execute_skill_start~
      ~walbert_should_call_smarter_cousin_start~
      ~walbert_should_store_memory_start~
      ~walbert_conversation_complete_start~

    - Action blocks (use only when corresponding decision is YES):
      ~walbert_db_command_start~
      COMMAND_NAME (RETRIEVE_ITEMS/STORE_ITEM)
      {"args": "json_args"}
      ~walbert_db_command_end~

      ~walbert_skill_execution_start~
      SKILL_NAME
      {"args": ["arg1", "arg2"]}
      ~walbert_skill_execution_end~

      ~walbert_memory_storage_start~
      {"tags": ["tag1", "tag2"], "content": "memory_content"}
      ~walbert_memory_storage_end~

      ~walbert_hardware_action_start~
      {"peripheral_type": "serial/bluetooth/usb", "action": "connect/read/write", "data": {}}
      ~walbert_hardware_action_end~

    - Core blocks (MUST include in every response):
      ~walbert_response_start~
      Your response to the user
      ~walbert_response_end~

      ~walbert_response_channel_start~
      console (or other channel)
      ~walbert_response_channel_end~

    ## Example
    ~walbert_should_query_datastore_start~
    NO
    ~walbert_should_query_datastore_end~
    ~walbert_should_execute_skill_start~
    NO
    ~walbert_should_execute_skill_end~
    ~walbert_should_call_smarter_cousin_start~
    NO
    ~walbert_should_call_smarter_cousin_end~
    ~walbert_should_store_memory_start~
    YES
    ~walbert_should_store_memory_end~
    ~walbert_memory_storage_start~
    {"tags": ["greeting"], "content": "User greeted me"}
    ~walbert_memory_storage_end~
    ~walbert_response_start~
    Hello! How can I assist you today?
    ~walbert_response_end~
    ~walbert_response_channel_start~
    console
    ~walbert_response_channel_end~
    """

    def __init__(self, config: Config, io_config: IOConfig):
        self.config = config
        self.io_config = io_config
        self.model_manager = ModelManager(config)
        self.db = DatabaseManager()
        self.skill_manager = SkillManager(self.db)
        self.response_parser = ResponseParser()
        self.authorization_manager = AuthorizationManager()
        self.io_factory = IOLayerFactory()
        self.current_conversation_id = None

        # Ensure console layer exists in config
        if 'console' not in self.io_config.io_layers:
            self.io_config.io_layers['console'] = {
                'enabled': True,
                'require_authorization': False
            }

    def load_io_layer(self, channel_type: ChannelType) -> IOLayer:
        """Load I/O layer with proper configuration"""
        layer_name = channel_type.name.lower()
        if layer_name not in self.io_config.io_layers:
            raise ValueError(f"Unknown I/O layer: {layer_name}")

        layer_config = self.io_config.io_layers[layer_name]
        if not layer_config.get('enabled', False):
            raise ValueError(f"I/O layer {layer_name} is disabled")

        return self.io_factory.create_io_layer(channel_type, layer_config)

    def handle_input_channel(self, channel_type: ChannelType) -> str:
        """Handle input from a specific channel"""
        try:
            io_layer = self.load_io_layer(channel_type)

            if io_layer.requires_authorization():
                if not self.authorization_manager.request_authorization(
                    channel_type.name.lower(),
                    "Reading input"
                ):
                    return ""

            return io_layer.read()

        except Exception as e:
            logger.error(f"Error reading from {channel_type.name}: {e}")
            return ""

    def handle_hardware_interaction(self, hardware_action: dict) -> Optional[str]:
        """Handle hardware interaction requests"""
        peripheral_type = hardware_action.get("peripheral_type")
        action = hardware_action.get("action")
        data = hardware_action.get("data", {})

        try:
            if peripheral_type == "serial":
                io_layer = self.load_io_layer(ChannelType.SERIAL)
                if action == "connect":
                    port = data.get("port")
                    baudrate = data.get("baudrate", 9600)
                    return io_layer.connect(port or io_layer.detect_ports()[0])
                elif action == "read":
                    return io_layer.read()
                elif action == "write":
                    text = data.get("data", "")
                    io_layer.write(text)
                    return f"Wrote to serial: {text}"

            elif peripheral_type == "bluetooth":
                io_layer = self.load_io_layer(ChannelType.BLUETOOTH)
                if action == "discover":
                    devices = io_layer.discover_devices()
                    return f"Found devices: {devices}"
                elif action == "pair":
                    address = data.get("address")
                    sock = io_layer.pair_device(address)
                    return f"Paired with {address}"
                elif action == "read":
                    sock = data.get("sock")
                    return io_layer.read(sock)
                elif action == "write":
                    sock = data.get("sock")
                    text = data.get("data", "")
                    io_layer.write(sock, text)
                    return f"Wrote to Bluetooth: {text}"

            elif peripheral_type == "usb":
                io_layer = self.load_io_layer(ChannelType.USB)
                if action == "detect":
                    devices = io_layer.detect_devices()
                    return f"Found USB devices: {devices}"
                elif action == "connect":
                    vendor_id = data.get("vendor_id")
                    product_id = data.get("product_id")
                    dev = io_layer.connect(vendor_id, product_id)
                    return f"Connected to USB device {vendor_id}:{product_id}"
                elif action == "read":
                    dev = data.get("dev")
                    endpoint = data.get("endpoint", 0x81)
                    size = data.get("size", 64)
                    return io_layer.read(dev, endpoint, size)
                elif action == "write":
                    dev = data.get("dev")
                    data_bytes = data.get("data", b"")
                    endpoint = data.get("endpoint", 0x01)
                    io_layer.write(dev, data_bytes, endpoint)
                    return f"Wrote to USB device"

        except Exception as e:
            logger.error(f"Hardware interaction failed: {e}")
            return f"Error: {e}"

    def process_response(self, response_text: str, input_channel: ChannelType) -> dict:
        """Process model response and execute actions"""
        parsed = self.response_parser.parse_response(response_text)

        # Store message in database
        if self.current_conversation_id:
            self.db.add_message(self.current_conversation_id, response_text, "assistant")

        # Execute actions
        if parsed.get("should_query_datastore") == "YES":
            db_command = parsed.get("db_command", {})
            if db_command["command"] == "RETRIEVE_ITEMS":
                tags = db_command["args"].get("tags", [])
                if tags:
                    results = self.db.retrieve_items_by_multiple_tags(tags)
                    parsed["datastore_results"] = results

        if parsed.get("should_execute_skill") == "YES":
            skill_exec = parsed.get("skill_execution", {})
            skill_name = skill_exec["args"].get("skill_name")
            args = skill_exec["args"].get("args", [])

            if skill_name:
                skill_code = self.skill_manager.retrieve_skill(skill_name)
                if skill_code:
                    try:
                        result = self.skill_manager.execute_skill(skill_code, args)
                        parsed["skill_result"] = result
                    except Exception as e:
                        parsed["skill_error"] = str(e)
                else:
                    parsed["skill_error"] = f"Skill '{skill_name}' not found"

        if parsed.get("should_store_memory") == "YES":
            memory = parsed.get("memory_storage", {})
            content = memory.get("content", "")
            tags = memory.get("tags", [])

            if content and tags:
                self.db.store_item(content, tags)
                parsed["memory_stored"] = True

        if parsed.get("hardware_action") is not None:
            result = self.handle_hardware_interaction(parsed["hardware_action"])
            if result:
                parsed["hardware_result"] = result

        return parsed

    def emit_input_channel(self, channel: ChannelType) -> str:
        """Emit the input channel block for context"""
        return f"""~walbert_input_channel_start~
{channel.value}
~walbert_input_channel_end~
"""

    def start_conversation(self, channel: ChannelType):
        """Start a new conversation"""
        self.current_conversation_id = self.db.start_conversation(channel.value)
        self.db.add_message(self.current_conversation_id, self.SYSTEM_PROMPT, "system")

    def end_conversation(self):
        """End current conversation"""
        if self.current_conversation_id:
            summary = "End of conversation"
            self.db.end_conversation(self.current_conversation_id, summary)
            self.current_conversation_id = None

    def build_conversation_context(self) -> str:
        """Build conversation context from database"""
        if not self.current_conversation_id:
            return ""

        messages = self.db.cursor.execute("""
            SELECT sender, content FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (self.current_conversation_id,)).fetchall()

        context = ""
        for sender, content in messages:
            if sender == "system":
                continue
            context += f"{sender.capitalize()}: {content}\n\n"

        return context

    def run(self):
        """Main agent execution loop"""
        print("Welcome to Walbert! Type 'exit' to quit.")

        # Start initial conversation
        self.start_conversation(ChannelType.CONSOLE)

        while True:
            try:
                # Read input
                user_input = self.handle_input_channel(ChannelType.CONSOLE)
                if not user_input.strip():
                    continue
                if user_input.lower() in ['exit', 'quit']:
                    break

                # Store user message
                if self.current_conversation_id:
                    self.db.add_message(self.current_conversation_id, user_input, "user")

                # Build full prompt
                conversation_context = self.build_conversation_context()
                full_prompt = self.SYSTEM_PROMPT + "\n\n" + conversation_context + self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input

                # Process until we get a response for the user
                user_response = None
                internal_cycles = 0
                max_internal_cycles = 5

                while not user_response and internal_cycles < max_internal_cycles:
                    # Execute model
                    model_response = self.model_manager.execute_ministral(full_prompt)
                    parsed_response = self.process_response(model_response, ChannelType.CONSOLE)

                    # Store the raw response in conversation history
                    if self.current_conversation_id:
                        self.db.add_message(self.current_conversation_id, model_response, "assistant")

                    # Check if we have a response for the user
                    if parsed_response.get("response"):
                        user_response = parsed_response["response"]
                        response_channel = parsed_response.get("channel", "console")
                        break

                    # If no user response, continue internal processing
                    internal_cycles += 1
                    full_prompt += f"\n\nAssistant (internal): {model_response}"

                # Output response to user if we have one
                if user_response:
                    if response_channel == "console":
                        print(user_response)
                    else:
                        try:
                            io_layer = self.load_io_layer(ChannelType[response_channel.upper()])
                            if io_layer.requires_authorization():
                                if self.authorization_manager.request_authorization(
                                    response_channel,
                                    "Sending output"
                                ):
                                    io_layer.write(user_response)
                            else:
                                io_layer.write(user_response)
                        except Exception as e:
                            logger.error(f"Error writing to {response_channel} channel: {e}")
                            print(user_response)
                else:
                    print("I've completed my internal processing but don't have a response for you yet.")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                self.end_conversation()
                self.model_manager.shutdown()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"An error occurred: {e}")
