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
    1. Evaluate if datastore query is needed (~walbert_should_query_datastore~).
    2. Evaluate if skill execution is needed (~walbert_should_execute_skill~).
    3. Evaluate if Devstral-24B should be called (~walbert_should_call_smarter_cousin~).
    4. Evaluate if memory should be stored (~walbert_should_store_memory~).
    5. Emit final response (~walbert_response~).

    ## Available Blocks
    - Decision: should_call_smarter_cousin, should_query_datastore, should_execute_skill, should_store_memory, conversation_complete
    - Action: db_command, skill_execution, memory_storage, hardware_action
    - Core: response, response_channel

    ## Example
    ~walbert_should_query_datastore_start~
    YES
    ~walbert_should_query_datastore_end~
    ~walbert_db_command_start~
    RETRIEVE_ITEMS
    {"tags": ["example"]}
    ~walbert_db_command_end~
    ~walbert_response_start~
    Here is the retrieved data.
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

    def load_io_layer(self, channel_type: ChannelType) -> IOLayer:
        """Load I/O layer with proper configuration"""
        layer_name = channel_type.value
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

    def process_response(self, response_text: str, input_channel: ChannelType) -> str:
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
                    response_text += f"\n\nDatastore Results: {results}"

        if parsed.get("should_execute_skill") == "YES":
            skill_exec = parsed.get("skill_execution", {})
            skill_name = skill_exec["args"].get("skill_name")
            args = skill_exec["args"].get("args", [])

            if skill_name:
                skill_code = self.skill_manager.retrieve_skill(skill_name)
                if skill_code:
                    try:
                        result = self.skill_manager.execute_skill(skill_code, args)
                        response_text += f"\n\nSkill Result: {result}"
                    except Exception as e:
                        response_text += f"\n\nSkill Execution Error: {e}"
                else:
                    response_text += f"\n\nError: Skill '{skill_name}' not found"

        if parsed.get("should_store_memory") == "YES":
            memory = parsed.get("memory_storage", {})
            content = memory["args"].get("content", "")
            tags = memory["args"].get("tags", [])

            if content and tags:
                self.db.store_item(content, tags)
                response_text += "\n\nMemory stored successfully"

        if parsed.get("hardware_action") is not None:
            hardware_action = parsed["hardware_action"]
            result = self.handle_hardware_interaction(hardware_action)
            if result:
                response_text += f"\n\nHardware Result: {result}"

        return response_text

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
                    self.db.add_message(self.current_conversation_id, user_input)

                # Build full prompt
                full_prompt = self.SYSTEM_PROMPT + "\n\n" + self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input

                # Process until conversation is complete
                conversation_active = True
                response_text = ""

                while conversation_active:
                    # Execute model
                    model_response = self.model_manager.execute_ministral(full_prompt)
                    response_text = self.process_response(model_response, ChannelType.CONSOLE)

                    # Parse response
                    parsed = self.response_parser.parse_response(response_text)

                    # Check if conversation should continue
                    if parsed.get("conversation_complete") == "YES":
                        conversation_active = False

                    # Update full prompt with response
                    full_prompt += f"\n\nAssistant: {response_text}"

                # Output final response
                if response_text:
                    print(response_text)

                # Check if conversation should end
                parsed = self.response_parser.parse_response(response_text)
                if parsed.get("conversation_complete") == "YES":
                    self.end_conversation()
                    print("\nConversation ended.")
                    self.start_conversation(ChannelType.CONSOLE)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                self.end_conversation()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"An error occurred: {e}")
