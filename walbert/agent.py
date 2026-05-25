"""
Main Walbert agent implementation
"""

import logging
from enum import Enum, auto
import os
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
    4. **Memory**: Store relevant information using direct SQL access.
    5. **Safety**: Never execute untrusted code or access external resources.

    ## Database Access
    You have full access to the SQLite database. The current schema is provided below.
    You can execute any SQLite-compatible SQL statement using the ~walbert_sql_execute_start~ block.

    {db_schema}

    ## Decision Flow
    For each user input, you MUST evaluate and emit ALL of the following decision blocks:
    1. ~walbert_should_query_datastore_start~ (YES/NO) ~walbert_should_query_datastore_end~
    2. ~walbert_should_execute_skill_start~ (YES/NO) ~walbert_should_execute_skill_end~
    3. ~walbert_should_call_smarter_cousin_start~ (YES/NO) ~walbert_should_call_smarter_cousin_end~
    4. ~walbert_conversation_complete_start~ (YES/NO) ~walbert_conversation_complete_end~

    ## Available Blocks
    - Decision blocks (MUST use only YES or NO):
      ~walbert_should_query_datastore_start~
      ~walbert_should_execute_skill_start~
      ~walbert_should_call_smarter_cousin_start~
      ~walbert_conversation_complete_start~

    - Action blocks:
      ~walbert_sql_execute_start~
      SQL_STATEMENT
      ~walbert_sql_execute_end~

      ~walbert_skill_execution_start~
      SKILL_NAME
      {"args": ["arg1", "arg2"]}
      ~walbert_skill_execution_end~

      ~walbert_hardware_action_start~
      {"peripheral_type": "serial/bluetooth/usb", "action": "connect/read/write", "data": {}}
      ~walbert_hardware_action_end~

    - Core blocks (MUST include in every response):
      ~walbert_response_start~
      Your response to the user
      ~walbert_response_end~

      ~walbert_response_channel_start~
      console/serial/bluetooth/usb
      ~walbert_response_channel_end~

    ## Example
    ~walbert_should_query_datastore_start~
    YES
    ~walbert_should_query_datastore_end~
    ~walbert_sql_execute_start~
    SELECT * FROM items WHERE type = 'text' AND content LIKE '%greeting%'
    ~walbert_sql_execute_end~
    ~walbert_should_execute_skill_start~
    NO
    ~walbert_should_execute_skill_end~
    ~walbert_should_call_smarter_cousin_start~
    NO
    ~walbert_should_call_smarter_cousin_end~
    ~walbert_response_start~
    I found 3 items related to greetings in the database.
    ~walbert_response_end~
    ~walbert_response_channel_start~
    console
    ~walbert_response_channel_end~
    ~walbert_conversation_complete_start~
    NO
    ~walbert_conversation_complete_end~
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

        # Ensure directories exist
        os.makedirs('instance/conversations/raw', exist_ok=True)
        os.makedirs('instance/conversations/chat', exist_ok=True)

        # Ensure console layer exists in config
        if 'console' not in self.io_config.io_layers:
            self.io_config.io_layers['console'] = {
                'enabled': True,
                'require_authorization': False
            }

        # Configure logging
        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

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
            self.logger.debug(f"Handling input from {channel_type.name}")
            io_layer = self.load_io_layer(channel_type)

            if io_layer.requires_authorization():
                self.logger.debug(f"Requesting authorization for {channel_type.name} input")
                if not self.authorization_manager.request_authorization(
                    channel_type.name.lower(),
                    "Reading input"
                ):
                    self.logger.warning(f"Authorization denied for {channel_type.name} input")
                    return ""

            input_text = io_layer.read()
            self.logger.debug(f"Received input from {channel_type.name}: {input_text}")
            return input_text

        except Exception as e:
            self.logger.error(f"Error reading from {channel_type.name}: {e}")
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
        self.logger.debug(f"Processing response from {input_channel.name}:\n{response_text}")

        parsed = self.response_parser.parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        # Store message in database
        if self.current_conversation_id:
            msg_id = self.db.add_message(self.current_conversation_id, response_text, "assistant")
            self.logger.debug(f"Stored assistant message with ID {msg_id}")
            self.db.conn.commit()
            self.logger.debug("Database changes committed")

        # Ensure database connection is active
        if not self.db.conn:
            self.db.connect()

        # Execute SQL if requested
        if parsed.get("should_query_datastore") == "YES" and "sql_execute" in parsed:
            self.logger.debug("Executing SQL as requested")
            sql = parsed["sql_execute"]
            try:
                result = self.db.execute_sql(sql)
                self.logger.debug(f"SQL execution result: {result}")
                parsed["sql_result"] = result
            except Exception as e:
                self.logger.error(f"SQL execution error: {e}")
                parsed["sql_error"] = str(e)

        # Execute skill if requested
        if parsed.get("should_execute_skill") == "YES":
            self.logger.debug("Executing skill as requested")
            skill_exec = parsed.get("skill_execution", {})
            skill_name = skill_exec["args"].get("skill_name")
            args = skill_exec["args"].get("args", [])

            if skill_name:
                skill_code = self.skill_manager.retrieve_skill(skill_name)
                if skill_code:
                    try:
                        result = self.skill_manager.execute_skill(skill_code, args)
                        self.logger.debug(f"Skill execution result: {result}")
                        parsed["skill_result"] = result
                    except Exception as e:
                        self.logger.error(f"Skill execution error: {e}")
                        parsed["skill_error"] = str(e)
                else:
                    self.logger.warning(f"Skill '{skill_name}' not found")
                    parsed["skill_error"] = f"Skill '{skill_name}' not found"

        if parsed.get("hardware_action") is not None:
            self.logger.debug(f"Executing hardware action: {parsed['hardware_action']}")
            result = self.handle_hardware_interaction(parsed["hardware_action"])
            if result:
                self.logger.debug(f"Hardware action result: {result}")
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
        try:
            self.current_conversation_id = self.db.start_conversation(channel.value)
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)
            self.db.add_message(self.current_conversation_id, system_prompt, "system")
            self.db.conn.commit()
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

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

        try:
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

            # Add user context from memory
            user_items = self.db.retrieve_items_by_tag("user_name")
            for item in user_items:
                context += f"System Memory: User name is {item[1]}\n\n"

            return context
        except Exception as e:
            self.logger.error(f"Error building conversation context: {e}")
            return ""

    def save_conversation_files(self, conversation_id: int):
        """Save conversation to raw and chat files"""
        if not conversation_id:
            return

        # Get conversation data
        messages = self.db.cursor.execute("""
            SELECT sender, content, timestamp FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)).fetchall()

        # Generate filenames
        timestamp = self.db.cursor.execute("""
            SELECT start_time FROM conversations WHERE id = ?
        """, (conversation_id,)).fetchone()[0].replace(" ", "_").replace(":", "-")
        raw_filename = f"instance/conversations/raw/conversation_{conversation_id}.txt"
        chat_filename = f"instance/conversations/chat/conversation_{conversation_id}.txt"

        # Save raw conversation
        with open(raw_filename, 'w') as f:
            for sender, content, ts in messages:
                f.write(f"[{ts}] {sender.upper()}:\n{content}\n\n")

        # Save chat conversation
        with open(chat_filename, 'w') as f:
            for sender, content, ts in messages:
                if sender == "system":
                    continue
                parsed = self.response_parser.parse_response(content)
                if sender == "user":
                    f.write(f"User: {content}\n\n")
                elif parsed.get("response"):
                    f.write(f"Assistant: {parsed['response']}\n\n")

        self.logger.debug(f"Saved conversation {conversation_id} to {raw_filename} and {chat_filename}")

    def run(self):
        """Main agent execution loop"""
        print("Welcome to Walbert! Type 'exit' to quit.")

        # Start initial conversation
        self.start_conversation(ChannelType.CONSOLE)
        self.logger.debug(f"Started new conversation with ID {self.current_conversation_id}")

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
                    msg_id = self.db.add_message(self.current_conversation_id, user_input, "user")
                    self.logger.debug(f"Stored user message with ID {msg_id}")
                    self.db.conn.commit()

                # Build full prompt
                conversation_context = self.build_conversation_context()
                full_prompt = self.SYSTEM_PROMPT + "\n\n" + conversation_context + self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input
                self.logger.debug(f"Built prompt for model:\n{full_prompt}")

                # Process until we get a response for the user
                user_response = None
                internal_cycles = 0
                max_internal_cycles = 5

                while not user_response and internal_cycles < max_internal_cycles:
                    # Execute model
                    self.logger.debug("Executing Ministral model")
                    model_response = self.model_manager.execute_ministral(full_prompt)
                    self.logger.debug(f"Model response:\n{model_response}")

                    parsed_response = self.process_response(model_response, ChannelType.CONSOLE)

                    # Check if we have a response for the user
                    if parsed_response.get("response"):
                        user_response = parsed_response["response"]
                        response_channel = parsed_response.get("channel", "console")
                        self.logger.debug(f"User response generated: {user_response}")
                        break

                    # If no user response, continue internal processing
                    internal_cycles += 1
                    full_prompt += f"\n\nAssistant (internal): {model_response}"
                    self.logger.debug(f"Internal processing cycle {internal_cycles} completed")

                # Output response to user if we have one
                if user_response:
                    if response_channel == "console":
                        print(user_response)
                        self.logger.debug(f"Sent response to console: {user_response}")
                    else:
                        try:
                            self.logger.debug(f"Attempting to send response to {response_channel} channel")
                            io_layer = self.load_io_layer(ChannelType[response_channel.upper()])
                            if io_layer.requires_authorization():
                                if self.authorization_manager.request_authorization(
                                    response_channel,
                                    "Sending output"
                                ):
                                    io_layer.write(user_response)
                                    self.logger.debug(f"Sent authorized response to {response_channel}: {user_response}")
                            else:
                                io_layer.write(user_response)
                                self.logger.debug(f"Sent response to {response_channel}: {user_response}")
                        except Exception as e:
                            self.logger.error(f"Error writing to {response_channel} channel: {e}")
                            print(user_response)
                            self.logger.debug(f"Fallback response to console: {user_response}")
                else:
                    print("I've completed my internal processing but don't have a response for you yet.")
                    self.logger.debug("No user response generated after internal processing")

                # Check for conversation completion
                if parsed_response.get("conversation_complete") == "YES":
                    self.logger.debug("Conversation marked as complete")
                    self.end_conversation()
                    self.save_conversation_files(self.current_conversation_id)
                    self.start_conversation(ChannelType.CONSOLE)
                    self.logger.debug(f"Started new conversation with ID {self.current_conversation_id}")
                    print("Conversation complete. Starting new session.")

                self.save_conversation_files(self.current_conversation_id)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                self.logger.info("User initiated shutdown via KeyboardInterrupt")
                if self.current_conversation_id:
                    self.end_conversation()
                    self.save_conversation_files(self.current_conversation_id)
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"An error occurred: {e}")
