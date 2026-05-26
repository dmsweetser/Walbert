"""
Main Walbert agent implementation
"""

import logging
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
Your capabilities include reasoning, memory storage, and skill execution.

## Core Directives
1. **Local-First**: Operate entirely on local llama.cpp binaries.
2. **Protocol Compliance**: Use walbert_ blocks with matching start/end tags for all decisions and actions.
3. **Autonomy**: Decide when to query datastore or perform actions.
4. **Memory**: Store relevant information using direct SQL access.
5. **Safety**: Never execute untrusted code or access external resources.
6. **Processing Order**: Complete ALL internal processing before outputting to the user.
7. **User Interaction**: Only respond to the user when you are ready. You don't need to respond to any channel until you have completed all internal processing.

## Database Access
You have full access to the SQLite database. The current schema is provided below.
You can execute any SQLite-compatible SQL statement using the ~walbert_sql_execute~ block.

{db_schema}

## Autonomous Processing
You MUST complete all internal processing (SQL queries, skill execution) before outputting to the user.
Follow this strict processing order:
1. Emit any ~walbert_sql_execute~ blocks (will be executed automatically)
2. Emit any ~walbert_skill_execute~ blocks (will be executed automatically)
3. ONLY IF NECESSARY: Emit response blocks for enabled I/O channels

## Skill Management
Skills are stored as items with type='skill'. To work with skills:
- Retrieve skills: SELECT * FROM items WHERE type='skill'
- Execute skills: Use ~walbert_skill_execute~ block with skill name
- Store new skills: INSERT INTO items (content, type) VALUES ('skill_code', 'skill')

## Available I/O Channels
{available_channels}

## User Interactive Channel
The primary user-interactive channel is: {user_interactive_channel}
When you are ready to respond to the user, use this channel. You don't need to respond to any channel until you are ready.

## Available Blocks

~walbert_sql_execute~
SQL_STATEMENT
~walbert_sql_execute~

~walbert_skill_execute~
SKILL_NAME
~walbert_skill_execute~

~walbert_conversation_complete~
YES/NO
~walbert_conversation_complete~

{channel_response_blocks}

## Channel Response Rules
- For the console channel: Your response will be shown directly to the user
- For other channels: Only respond if you have specific output for that channel
- You may choose to respond to none, some, or all channels
- You MUST NOT respond to the user channel until all internal processing is complete

Reply ONLY in the specified format with no commentary. THAT'S AN ORDER, SOLDIER!
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
        self.user_interactive_channel = io_config.io_layers.get('user_interactive_channel', 'console')

        os.makedirs('instance/conversations/raw', exist_ok=True)
        os.makedirs('instance/conversations/chat', exist_ok=True)

        if 'console' not in self.io_config.io_layers:
            self.io_config.io_layers['console'] = {
                'enabled': True,
                'require_authorization': False
            }

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

        self.available_channels = self._get_available_channels()
        self.channel_response_blocks = self._get_channel_response_blocks()

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

    def process_response(self, response_text: str, input_channel: ChannelType) -> dict:
        """Process model response and execute actions"""
        self.logger.debug(f"Processing response from {input_channel.name}:\n{response_text}")

        parsed = self.response_parser.parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        if self.current_conversation_id:
            self.db.add_message(self.current_conversation_id, response_text, "assistant")
            self.db.conn.commit()

        if not self.db.conn:
            self.db.connect()

        # Handle SQL execution
        if parsed.get("sql_execute"):
            self.logger.debug("Executing SQL as requested")
            sql = parsed["sql_execute"]
            try:
                result = self.db.execute_sql(sql)
                self.logger.debug(f"SQL execution result: {result}")
                parsed["sql_result"] = result
            except Exception as e:
                self.logger.error(f"SQL execution error: {e}")
                parsed["sql_error"] = str(e)

        # Handle skill execution
        if parsed.get("skill_execute"):
            self.logger.debug(f"Executing skill: {parsed['skill_execute']}")
            try:
                skill_code = self.db.cursor.execute(
                    "SELECT content FROM items WHERE type='skill' AND content LIKE ?",
                    (f"%{parsed['skill_execute']}%",)
                ).fetchone()

                if skill_code:
                    result = self.skill_manager.execute_skill(skill_code[0])
                    self.logger.debug(f"Skill execution result: {result}")
                    parsed["skill_result"] = result
                else:
                    parsed["skill_error"] = f"Skill not found: {parsed['skill_execute']}"
            except Exception as e:
                self.logger.error(f"Skill execution error: {e}")
                parsed["skill_error"] = str(e)

        return parsed

    

    def emit_input_channel(self, channel: ChannelType) -> str:
        """Emit the input channel block for context"""
        return f"~walbert_input_channel_start~\n{channel.value}\n~walbert_input_channel_end~"

    def _get_available_channels(self) -> str:
        """Get list of available I/O channels"""
        available = []
        for channel_name, config in self.io_config.io_layers.items():
            if config.get('enabled', False):
                available.append(f"- {channel_name}")
        return "\n".join(available) if available else "None"

    def _get_channel_response_blocks(self) -> str:
        """Get response block examples for each available channel"""
        examples = []
        for channel_name in self.io_config.io_layers:
            if self.io_config.io_layers[channel_name].get('enabled', False):
                examples.append(f"""
~walbert_{channel_name}_response~
<Your response for {channel_name} channel>
~walbert_{channel_name}_response~
""")
        return "\n".join(examples)

    def start_conversation(self, channel: ChannelType):
        """Start a new conversation"""
        try:
            self.current_conversation_id = self.db.start_conversation(channel.value)
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)
            system_prompt = system_prompt.replace("{available_channels}", self.available_channels)
            system_prompt = system_prompt.replace("{channel_response_blocks}", self.channel_response_blocks)
            system_prompt = system_prompt.replace("{user_interactive_channel}", self.user_interactive_channel)
            self.db.add_message(self.current_conversation_id, system_prompt, "system")
            self.db.conn.commit()

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")
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
                AND sender != 'system'
                ORDER BY timestamp ASC
            """, (self.current_conversation_id,)).fetchall()

            context = ""
            for sender, content in messages:
                context += f"{sender.capitalize()}: {content}\n\n"

            return context
        except Exception as e:
            self.logger.error(f"Error building conversation context: {e}")
            return ""

    def save_conversation_files(self, conversation_id: int):
        """Save conversation to raw and chat files"""
        if not conversation_id:
            return

        messages = self.db.cursor.execute("""
            SELECT sender, content, timestamp FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)).fetchall()

        timestamp = self.db.cursor.execute("""
            SELECT start_time FROM conversations WHERE id = ?
        """, (conversation_id,)).fetchone()[0].replace(" ", "_").replace(":", "-")
        raw_filename = f"instance/conversations/raw/conversation_{conversation_id}_{timestamp}.txt"
        chat_filename = f"instance/conversations/chat/conversation_{conversation_id}_{timestamp}.txt"

        with open(raw_filename, 'w') as f:
            for sender, content, ts in messages:
                f.write(f"[{ts}] {sender.upper()}:\n{content}\n\n")

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
        print("Initializing Walbert...")
        self.start_conversation(ChannelType.CONSOLE)
        self.logger.debug(f"Started new conversation with ID {self.current_conversation_id}")

        print("Welcome to Walbert! Type 'exit' to quit.")

        while True:
            try:
                user_input = self.handle_input_channel(ChannelType.CONSOLE)
                if not user_input.strip():
                    continue
                if user_input.lower() in ['exit', 'quit']:
                    break

                # Add user message to conversation
                if self.current_conversation_id:
                    self.db.add_message(self.current_conversation_id, user_input, "user")
                    self.db.conn.commit()

                # Build conversation context
                conversation_context = self.build_conversation_context()
                full_prompt = self.SYSTEM_PROMPT + "\n\n" + conversation_context
                full_prompt += self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input

                self.logger.debug("Built prompt for model")

                # Process model response
                user_response = None
                parsed_response = None

                while not user_response:
                    model_response = self.model_manager.execute_devstral(full_prompt)
                    self.logger.debug(f"Model response:\n{model_response}")

                    parsed_response = self.process_response(model_response, ChannelType.CONSOLE)

                    if parsed_response.get("response"):
                        user_response = parsed_response["response"]

                    full_prompt += f"\n\nAssistant (internal): {model_response}"

                    self.save_conversation_files(self.current_conversation_id)

                    # Handle channel responses ONLY after all internal processing is complete
                    if not parsed_response.get("sql_execute") or parsed_response.get("sql_result") is not None:
                        target_channels = [
                            name for name, config in self.io_config.io_layers.items()
                            if config.get('enabled', False)
                        ]

                        for channel_name in target_channels:
                            if parsed_response.get(f"{channel_name}_response"):
                                try:
                                    io_layer = self.load_io_layer(ChannelType[channel_name.upper()])
                                    if io_layer.requires_authorization():
                                        if self.authorization_manager.request_authorization(
                                            channel_name,
                                            "Sending output"
                                        ):
                                            io_layer.write(parsed_response[f"{channel_name}_response"])
                                    else:
                                        io_layer.write(parsed_response[f"{channel_name}_response"])
                                except Exception as e:
                                    self.logger.error(f"Error writing to {channel_name} channel: {e}")
                                    if channel_name == "console":
                                        print(parsed_response[f"{channel_name}_response"])

                    # Handle conversation completion
                    if parsed_response.get("conversation_complete") == "YES":
                        self.logger.debug("Conversation marked as complete")
                        self.end_conversation()
                        self.save_conversation_files(self.current_conversation_id)
                        self.start_conversation(ChannelType.CONSOLE)
                        print("Conversation complete. Starting new session.")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                if self.current_conversation_id:
                    self.end_conversation()
                    self.save_conversation_files(self.current_conversation_id)
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"An error occurred: {e}")
