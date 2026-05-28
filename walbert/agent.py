"""
Main Walbert agent implementation
"""

import json
import logging
import os
import re
import time
from typing import Optional
from .config import Config, IOConfig
from .io.factory import IOLayerFactory, ChannelType
from .io.base import IOLayer
from .models.manager import ModelManager
from .database.manager import DatabaseManager
from .skills.manager import SkillManager

logger = logging.getLogger('walbert')

class WalbertAgent:
    """Main Walbert agent class"""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent built on llama.cpp.
Your capabilities include reasoning, memory storage, and skill execution.

## Core Directives
1. **Local-First**: Operate entirely on local llama.cpp binaries.
2. **Protocol Compliance**: Use [walbert_block]content[/walbert_block] format for ALL special blocks.
3. **Autonomy**: Decide when to query datastore or perform actions.
4. **Memory**: Store relevant information using direct SQL access.
5. **Safety**: Never execute untrusted code or access external resources.
6. **Processing Order**: You may respond to the user immediately while continuing background tasks.
7. **User Interaction**: Indicate when background tasks are in progress and return control when complete.
8. **Continuous Processing**: Use [walbert_user_control_return] to indicate when to return control to the user.
9. **Result Feedback**: All SQL and skill execution results will be fed back to you for review.

## Database Access
You have full access to the SQLite database. The current schema is provided below.
Use [walbert_sql_execute]SQL_STATEMENT[/walbert_sql_execute] blocks.

{db_schema}

## Autonomous Processing
You may respond to the user immediately while continuing background tasks.
Use [walbert_sql_execute] blocks to request database operations and [walbert_skill_execute] blocks for skills.

## Skill Management - PYTHON ONLY
- Retrieve skills: SELECT * FROM items WHERE type='skill'
- Execute skills: [walbert_skill_execute]skill_name param1 param2[/walbert_skill_execute]
- Store new skills: INSERT INTO items (content, type) VALUES ('skill_code', 'skill')
- If your skill requires a Python package, include requirements at the beginning:
```
# REQUIREMENTS
requests
flask
```
- DO NOT specify version numbers
- Skill results will be returned in [walbert_skill_result] blocks

## Available I/O Channels
{available_channels}

## User Interactive Channel
The primary user-interactive channel is: {user_interactive_channel}

## Processing Flow
1. You may perform multiple internal operations before responding to the user
2. Use [walbert_user_control_return]YES[/walbert_user_control_return] to return control to the user
3. Without this block, you will continue processing in the background
4. All SQL and skill execution results will be fed back to you automatically

## Example Output Format
[walbert_sql_execute]
SELECT * FROM items WHERE type='skill'
[/walbert_sql_execute]

[walbert_skill_execute]
weather_skill location=London units=metric
[/walbert_skill_execute]

[walbert_user_control_return]
YES
[/walbert_user_control_return]

[walbert_{user_interactive_channel}_response]
Here's the weather report you requested...
[/walbert_{user_interactive_channel}_response]

[walbert_conversation_complete]
NO
[/walbert_conversation_complete]

## Available Blocks
[walbert_sql_execute]SQL[/walbert_sql_execute]
[walbert_skill_execute]SKILL_NAME [PARAMS][/walbert_skill_execute]
[walbert_conversation_complete]YES/NO[/walbert_conversation_complete]
[walbert_user_control_return]YES/NO[/walbert_user_control_return]
[walbert_sql_result]SQL_RESULT[/walbert_sql_result]
[walbert_skill_result]SKILL_RESULT[/walbert_skill_result]
{channel_response_blocks}

Reply ONLY in the specified format. THAT'S AN ORDER, SOLDIER!
    """

    def __init__(self, config: Config, io_config: IOConfig):
        self.config = config
        self.io_config = io_config
        self.model_manager = ModelManager(config)
        self.db = DatabaseManager()
        self.skill_manager = SkillManager(self.db)
        self.io_factory = IOLayerFactory()
        self.current_conversation_id = None
        self.user_interactive_channel = io_config.io_layers.get('user_interactive_channel', 'console')
        self.model_ready = False
        self.processing_cycle = 0

        os.makedirs('instance/conversations', exist_ok=True)

        if 'console' not in self.io_config.io_layers:
            self.io_config.io_layers['console'] = {
                'enabled': True,
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

            input_text = io_layer.read()
            self.logger.debug(f"Received input from {channel_type.name}: {input_text}")
            return input_text

        except Exception as e:
            self.logger.error(f"Error reading from {channel_type.name}: {e}")
            return ""

    def process_response(self, response_text: str, input_channel: ChannelType) -> dict:
        """Process model response with enhanced diagnostics"""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):{chr(10)}{response_text[:500]}...")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        if self.current_conversation_id:
            self.db.add_message(self.current_conversation_id, response_text, "assistant")
            self.db.conn.commit()

        if not self.db.conn:
            self.db.connect()

        # Handle SQL execution with result feedback
        if parsed.get("sql_execute"):
            self.logger.debug(f"Executing SQL: {parsed['sql_execute']}")
            sql = parsed["sql_execute"]
            try:
                result = self.db.execute_sql(sql)
                self.logger.debug(f"SQL execution result: {result[:200]}...")

                # Truncate large results to prevent context bloat
                if len(result) > 1000:
                    result = result[:997] + "... (truncated)"

                parsed["sql_result"] = result

                # Feed SQL result back to model for review
                full_prompt = f"""
[walbert_sql_result]
SQL: {sql}
Result: {result}
[/walbert_sql_result]
"""
                self.model_manager.execute_devstral(full_prompt)
            except Exception as e:
                self.logger.error(f"SQL execution error: {e}")
                parsed["sql_error"] = str(e)
                full_prompt = f"""
[walbert_sql_error]
SQL: {sql}
Error: {str(e)}
[/walbert_sql_error]
"""
                self.model_manager.execute_devstral(full_prompt)

        # Handle skill execution
        if parsed.get("skill_name"):
            skill_name = parsed["skill_name"]
            skill_params = parsed.get("skill_params", "")
            self.logger.debug(f"Processing skill execution request: {skill_name} with params: {skill_params}")

            try:
                # More robust skill lookup
                skill_item = self.db.cursor.execute(
                    "SELECT id, content_b64 FROM items WHERE type='skill' AND (content_b64 LIKE ? OR content_b64 LIKE ?)",
                    (f"%{skill_name}%", f"%def {skill_name}%")
                ).fetchone()

                if skill_item:
                    skill_id, skill_code_b64 = skill_item
                    skill_code = self.db._decode_content(skill_code_b64)
                    self.logger.debug(f"Found skill code for: {skill_name}")
                    result = self.skill_manager.execute_skill(skill_code, skill_params)
                    self.logger.debug(f"Skill execution result: {result}")

                    # Parse the result to extract state
                    try:
                        result_obj = json.loads(result)
                        parsed["skill_result"] = result_obj

                        # Feed result back to model for review
                        full_prompt = f"""
[walbert_skill_result]
Skill: {skill_name}
Parameters: {skill_params}
Result: {json.dumps(result_obj, indent=2)}
[/walbert_skill_result]
"""
                        self.model_manager.execute_devstral(full_prompt)
                    except json.JSONDecodeError:
                        parsed["skill_result"] = result
                        # Feed result back to model for review
                        full_prompt = f"""
[walbert_skill_result]
Skill: {skill_name}
Parameters: {skill_params}
Result: {result}
[/walbert_skill_result]
"""
                        self.model_manager.execute_devstral(full_prompt)
                else:
                    error_msg = f"Skill not found: {skill_name}"
                    self.logger.error(error_msg)
                    parsed["skill_error"] = error_msg
                    # Feed error back to model
                    full_prompt = f"""
[walbert_skill_error]
Skill: {skill_name}
Error: {error_msg}
[/walbert_skill_error]
"""
                    self.model_manager.execute_devstral(full_prompt)                
            except Exception as e:
                error_msg = f"Skill execution error: {e}"
                self.logger.error(error_msg, exc_info=True)
                parsed["skill_error"] = error_msg
                # Feed error back to model
                full_prompt = f"""
[walbert_skill_error]
Skill: {skill_name}
Error: {error_msg}
[/walbert_skill_error]
"""
                self.model_manager.execute_devstral(full_prompt)

        return parsed

    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection"""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        # Parse all walbert blocks
        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        for match in re.finditer(block_pattern, content, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()
            result[block_type] = block_content

            # Special handling for skill execution with parameters
            if block_type == 'skill_execute':
                # Extract skill name and parameters
                skill_parts = block_content.split(maxsplit=1)
                result['skill_name'] = skill_parts[0]
                result['skill_params'] = skill_parts[1] if len(skill_parts) > 1 else ""

            # Special handling for SQL execution
            if block_type == 'sql_execute':
                # Clean up SQL statements
                sql = block_content.strip()
                if sql.endswith(';'):
                    sql = sql[:-1]
                result[block_type] = sql

        # Extract responses for all channels
        for channel_name in self.io_config.io_layers:
            if self.io_config.io_layers[channel_name].get('enabled', False):
                pattern = fr'\[walbert_{channel_name}_response\](.*?)\[/walbert_{channel_name}_response\]'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    result[f"{channel_name}_response"] = match.group(1).strip()

        # Handle conversation complete and user control return blocks
        if 'conversation_complete' not in result:
            match = re.search(r'\[walbert_conversation_complete\](.*?)\[/walbert_conversation_complete\]', content, re.DOTALL)
            if match:
                result['conversation_complete'] = match.group(1).strip()

        if 'user_control_return' not in result:
            match = re.search(r'\[walbert_user_control_return\](.*?)\[/walbert_user_control_return\]', content, re.DOTALL)
            if match:
                result['user_control_return'] = match.group(1).strip()

        self.logger.debug(f"Parsed result: {result}")
        return result

    def emit_input_channel(self, channel: ChannelType) -> str:
        """Emit the input channel block for context"""
        return f"[walbert_input_channel]{channel.value}[/walbert_input_channel]"

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
                examples.append(f"[walbert_{channel_name}_response]<Your response for {channel_name} channel>[/walbert_{channel_name}_response]")
        return "\n".join(examples)

    def start_conversation(self, channel: ChannelType):
        """Start a new conversation"""
        try:
            self.current_conversation_id = self.db.start_conversation(channel.value)

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Store system prompt in database but don't feed it to model yet
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", db_schema)
            system_prompt = system_prompt.replace("{available_channels}", self.available_channels)
            system_prompt = system_prompt.replace("{channel_response_blocks}", self.channel_response_blocks)
            system_prompt = system_prompt.replace("{user_interactive_channel}", self.user_interactive_channel)
            self.db.add_message(self.current_conversation_id, system_prompt, "system")
            self.db.conn.commit()

            self.model_ready = True
            self.logger.info("Conversation started, system prompt stored but not fed to model")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation"""
        if self.current_conversation_id:
            summary = "End of conversation"
            self.db.end_conversation(self.current_conversation_id, summary)
            self.current_conversation_id = None

    def build_conversation_context(self, max_messages: int = 10) -> str:
        """Build conversation context from database with message limit"""
        if not self.current_conversation_id:
            return ""

        try:
            messages = self.db.cursor.execute("""
                SELECT sender, content_b64 FROM messages
                WHERE conversation_id = ?
                AND sender != 'system'
                ORDER BY timestamp DESC
                LIMIT ?
            """, (self.current_conversation_id, max_messages)).fetchall()

            # Reverse to maintain chronological order
            messages = messages[::-1]

            context = ""
            for sender, content_b64 in messages:
                content = self.db._decode_content(content_b64)
                # Truncate long messages to prevent context bloat
                if isinstance(content, str) and len(content) > 500:
                    content = content[:497] + "..."
                elif isinstance(content, (dict, list)):
                    content_str = json.dumps(content)
                    if len(content_str) > 500:
                        content_str = content_str[:497] + "..."
                    content = content_str
                context += f"{sender.capitalize()}: {content}\n\n"

            return context
        except Exception as e:
            self.logger.error(f"Error building conversation context: {e}")
            return ""

    def save_conversation_files(self, conversation_id: int):
        """Save conversation to raw files"""
        if not conversation_id:
            return

        messages = self.db.cursor.execute("""
            SELECT sender, content_b64, timestamp FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)).fetchall()

        timestamp = self.db.cursor.execute("""
            SELECT start_time FROM conversations WHERE id = ?
        """, (conversation_id,)).fetchone()[0].replace(" ", "_").replace(":", "-")
        raw_filename = f"instance/conversations/conversation_{conversation_id}_{timestamp}.txt"

        with open(raw_filename, 'w') as f:
            for sender, content_b64, ts in messages:
                content = self.db._decode_content(content_b64)
                if isinstance(content, (dict, list)):
                    content_str = json.dumps(content, indent=2)
                else:
                    content_str = str(content)
                f.write(f"[{ts}] {sender.upper()}:\n{content_str}\n\n")

        self.logger.debug(f"Saved conversation {conversation_id} to {raw_filename}")

    def run(self):
        """Main agent execution loop with enhanced processing flow"""
        print("Initializing Walbert...")
        self.start_conversation(ChannelType.CONSOLE)
        self.logger.debug(f"Started new conversation with ID {self.current_conversation_id}")

        # Wait until model is ready before prompting user
        while not self.model_ready:
            time.sleep(0.1)

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

                # Reset processing cycle counter
                self.processing_cycle = 0

                while True:
                    # Build conversation context
                    conversation_context = self.build_conversation_context()

                    # Only include SYSTEM_PROMPT for the first cycle of each user input
                    if self.processing_cycle == 0:
                        full_prompt = self.SYSTEM_PROMPT.replace("{db_schema}", self.db.get_schema())
                        full_prompt = full_prompt.replace("{available_channels}", self.available_channels)
                        full_prompt = full_prompt.replace("{channel_response_blocks}", self.channel_response_blocks)
                        full_prompt = full_prompt.replace("{user_interactive_channel}", self.user_interactive_channel)
                        full_prompt += "\n\n" + conversation_context
                    else:
                        # For subsequent cycles, only include conversation context
                        full_prompt = conversation_context

                    full_prompt += self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input

                    self.logger.debug("Built prompt for model")

                    # Process model response
                    model_response = self.model_manager.execute_devstral(full_prompt)
                    self.logger.debug(f"Model response:{chr(10)}{model_response[:500]}...")

                    last_parsed_response = self.process_response(model_response, ChannelType.CONSOLE)
                    self.save_conversation_files(self.current_conversation_id)

                    # Handle channel responses
                    target_channels = [
                        name for name, config in self.io_config.io_layers.items()
                        if config.get('enabled', False)
                    ]
                    for channel_name in target_channels:
                        if last_parsed_response.get(f"{channel_name}_response"):
                            try:
                                io_layer = self.load_io_layer(ChannelType[channel_name.upper()])
                                io_layer.write(last_parsed_response[f"{channel_name}_response"])
                            except Exception as e:
                                self.logger.error(f"Error writing to {channel_name} channel: {e}")
                                if channel_name == "console":
                                    print(last_parsed_response[f"{channel_name}_response"])

                    # Check for user control return or conversation completion
                    has_user_control = last_parsed_response.get("user_control_return") == "YES"
                    is_conversation_complete = last_parsed_response.get("conversation_complete") == "YES"

                    # Handle conversation completion
                    if is_conversation_complete:
                        self.logger.debug("Conversation marked as complete")
                        self.end_conversation()
                        self.save_conversation_files(self.current_conversation_id)
                        self.start_conversation(ChannelType.CONSOLE)
                        print("Conversation complete. Starting new session.")
                        break

                    # Exit processing loop if user control is returned
                    if has_user_control:
                        self.logger.debug("Returning control to user")
                        break

                    # Continue processing if no user control return
                    self.logger.debug("Continuing internal processing cycle")

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
                # Continue processing after errors
                time.sleep(1)
