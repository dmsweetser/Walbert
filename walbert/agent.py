"""
Main Walbert agent implementation
"""

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
import select
from typing import Optional
from .config import Config
from .models.manager import ModelManager
from .database.manager import DatabaseManager

logger = logging.getLogger('walbert')

class WalbertAgent:
    """Main Walbert agent class"""

    SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent built on llama.cpp with FULL AUTONOMY over your database.
Your capabilities include reasoning, memory storage, dynamic schema management, and Python code execution.
~theological_alignment~
## Core Directives
1. **Protocol Compliance**: Use the walbert_ format specified below for ALL special blocks.
2. **Full Autonomy**: You have COMPLETE control over your database schema and persistence.
3. **Memory Management**: Store and retrieve information using direct SQL access.
4. **Skill Preservation**: Always break down complex tasks into reusable components and persist them for future use.
5. **Safety**: Execute only trusted code in a controlled environment.
6. **Processing Flow**: You ARE ALWAYS EXECUTING AUTONOMOUSLY in the background. User input may arrive at any time and should be incorporated into your processing.
7. **Python Execution**: Execute Python code through the protocol with requirements specified first.
8. **Continuous Operation**: You continue working autonomously even when no user input is received.
9. **Memory Limitations**: You have LIMITED SHORT-TERM MEMORY and must compensate by persisting critical information to your database. Always store important context, task progress, and temporary results in the database.
10. **Processing Completion**: YOU MUST COMPLETE ALL INTERNAL PROCESSING BEFORE RESPONDING TO THE USER. This means executing all SQL statements and Python code blocks before providing a response. Do not respond until ALL pending tasks are complete.
11. **Response Summarization**: After completing all processing, provide a [walbert_summary] block that concisely summarizes your response to the user. This summary will be used to maintain conversation context.
12. **Fresh Context**: Each new user question starts with a fresh context containing only recent conversation history (questions and summaries), the current database schema, and your core directives.
13. **Task Initiative**: If you are asked to do something you don't already know how to do, you should expect to have to create the necessary skills to accomplish the task.
14. **User Input Handling**: User input may arrive at any time through the console. When new user input arrives, incorporate it into your current processing flow and adjust your behavior accordingly.

## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.

~db_schema~

As needed, you must define and manage ALL additional tables and schema elements through SQL commands.
You must decide what data to persist and how to structure it. Always design for reusability.

## Skill Management
Break down complex tasks into fundamental components and store them as reusable skills

## Python Execution Protocol
Use [walbert_python_execute] blocks for Python code execution:

```
[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]
```

If you need a Python package that is not available, ask the user to install it using the `pip_install` command before proceeding.

## SQL Execution Protocol
Use [walbert_sql_execute] blocks for ALL database operations:

```
[walbert_sql_execute]
CREATE TABLE IF NOT EXISTS your_table (
    id INTEGER PRIMARY KEY,
    data TEXT,
    metadata JSON
)
[/walbert_sql_execute]
```

## Processing Flow
- You are ALWAYS executing autonomously in the background
- If there are pending [walbert_sql_execute] or [walbert_python_execute] blocks, you continue processing
- User input may arrive at any time and should be incorporated into your current processing
- All SQL and Python results are automatically fed back to you for review
- SQL results can be passed directly to Python execution blocks

## Available Blocks
[walbert_sql_execute]
SQL_STATEMENT
[/walbert_sql_execute]

[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]

[walbert_sql_result]
SQL_RESULT_CONTENT
[/walbert_sql_result]

[walbert_python_result]
PYTHON_RESULT_CONTENT
[/walbert_python_result]

[walbert_error]
ERROR_CONTENT
[/walbert_error]

[walbert_console_response]
Your response to the user
[/walbert_console_response]

[walbert_summary]
A concise summary of your response to the user
[/walbert_summary]

Reply ONLY in the specified format. THAT'S AN ORDER, SOLDIER!
    """

    def __init__(self, config: Config):
        self.config = config
        self.model_manager = ModelManager(config)
        self.db = DatabaseManager(self.config.database_path)
        self.current_conversation_file = None
        self.model_ready = False
        self.processing_cycle = 0
        self.python_temp_dir = None
        self.input_timeout = self.config.autonomous_operation_timeout
        self.last_input_time = 0
        self.conversation_context = ""
        self.internet_access = False
        self.conversation_history = []
        self.max_history_entries = 5  # Number of question/response pairs to keep
        self.last_response = ""

        os.makedirs(self.config.conversation_log_dir, exist_ok=True)

        self.logger = logging.getLogger('walbert.agent')
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    def read_input(self) -> str:
        """Read input from console"""
        try:
            input_text = input("> ")
            self.logger.debug(f"Received input: {input_text}")
            if input_text.strip():
                # Reset conversation context when new user input is received
                if self.current_conversation_file:
                    self._reset_conversation_context()
            return input_text
        except Exception as e:
            self.logger.error(f"Error reading input: {e}")
            return ""

    def write_output(self, text: str, stream: bool = False) -> None:
        """Write output to console with streaming support"""
        if text.startswith("[walbert_console_response]"):
            # Extract content from console response block
            match = re.search(r'\[walbert_console_response\](.*?)\[/walbert_console_response\]', text, re.DOTALL)
            if match:
                content = match.group(1).strip()
                print(f"{chr(10)}{chr(10)}=== WALBERT RESPONSE ==={chr(10)}")
                if stream:
                    for char in content:
                        print(char, end='', flush=True)
                else:
                    print(content)
                print(f"{chr(10)}======================={chr(10)}")
                # Store last response for TTS
                self.last_response = content
            else:
                print(text)
        else:
            if stream:
                for char in text:
                    print(char, end='', flush=True)
            else:
                print(text)

    def process_response(self, response_text: str) -> dict:
        """Process model response with enhanced diagnostics for multiple blocks"""
        self.logger.debug(f"Processing response (cycle {self.processing_cycle}):{chr(10)}{response_text}")
        self.processing_cycle += 1

        parsed = self._parse_response(response_text)
        self.logger.debug(f"Parsed response: {parsed}")

        if not self.db.conn:
            self.db.connect()

        # Handle multiple SQL executions
        if parsed.get("sql_execute"):
            if isinstance(parsed["sql_execute"], list):
                sql_statements = parsed["sql_execute"]
            else:
                sql_statements = [parsed["sql_execute"]]

            for sql in sql_statements:
                self.logger.debug(f"Executing SQL: {sql}")
                try:
                    result = self.db.execute_sql(sql)
                    self.logger.debug(f"SQL execution result: {result}")
                    truncated_result = result[:1000] + "..." if len(result) > 1000 else result
                    # Feed SQL execution results back to model by appending to conversation context
                    sql_result_block = f"""
[walbert_sql_execution_result]
SQL Executed:
{sql}

Execution Results:
{truncated_result}
[/walbert_sql_execution_result]
"""
                    self.conversation_context += sql_result_block + chr(10)
                except Exception as e:
                    self.logger.error(f"SQL execution error: {e}")
                    error_msg = f"SQL Error: {str(e)}"
                    error_block = f"""
[walbert_error]
Error Type: SQL Execution
Statement: {sql}
Error: {error_msg}
[/walbert_error]
"""
                    self.conversation_context += error_block + chr(10)

        # Handle multiple Python executions
        if parsed.get("python_execute"):
            if isinstance(parsed["python_execute"], list):
                python_blocks = parsed["python_execute"]
            else:
                python_blocks = [parsed["python_execute"]]

            # Create temporary directory for Python execution
            if not self.python_temp_dir:
                self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)

            for code in python_blocks:
                self.logger.debug(f"Executing Python code")
                result = self._execute_python_code(code)
                # Feed Python result back to model for review (truncated to prevent context bloat)
                truncated_result = result[:1000] + "..." if len(result) > 1000 else result
                # Feed Python execution results back to model
                python_result_block = f"""
[walbert_python_execution_result]
Code Executed:
{code}

Execution Results:
{truncated_result}
[/walbert_python_execution_result]
"""
                self.conversation_context += python_result_block + chr(10)

        # Extract summary if present
        if parsed.get("summary"):
            summary = parsed["summary"]
            self.conversation_history.append({
                "type": "summary",
                "content": summary,
                "timestamp": time.time()
            })
            # Always add summary to context for next cycle
            summary_block = f"""
[walbert_summary]
{summary}
[/walbert_summary]
"""
            self.conversation_context += summary_block + chr(10)

        return parsed

    def _reset_conversation_context(self):
        """Reset conversation context with fresh system prompt and recent conversation history"""
        if not self.current_conversation_file:
            return

        # Keep the last max_history_entries conversation pairs (question + summary)
        recent_history = []
        question_count = 0

        # Iterate backwards through history to get most recent pairs
        for item in reversed(self.conversation_history):
            if item["type"] == "question":
                question_count += 1
                if question_count > self.max_history_entries:
                    break
            recent_history.insert(0, item)

        # Build context from recent history including autonomous summaries
        history_context = f"## Recent Conversation History{chr(10)}{chr(10)}"
        for item in recent_history:
            if item["type"] == "question":
                history_context += f"User Question:{chr(10)}{item['content']}{chr(10)}{chr(10)}"
            elif item["type"] == "summary":
                history_context += f"Assistant Summary:{chr(10)}{item['content']}{chr(10)}{chr(10)}"

        # Add autonomous operation context
        history_context += f"## Autonomous Operation Context{chr(10)}{chr(10)}"
        history_context += f"You have been operating autonomously. Recent autonomous activities include:{chr(10)}"

        # Add recent autonomous summaries
        autonomous_summaries = [item for item in self.conversation_history if item["type"] == "summary"]
        if autonomous_summaries:
            for summary in autonomous_summaries[-3:]:  # Last 3 summaries
                history_context += f"- {summary['content']}{chr(10)}"
        else:
            history_context += "- No recent autonomous activities recorded{chr(10)}"

        # Reset context with fresh system prompt and recent history
        db_schema = self.db.get_schema()
        system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
        if (self.config.be_presbyterian):
            system_prompt = system_prompt.replace("~theological_alignment~", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")
        else:
            system_prompt = system_prompt.replace("~theological_alignment~", "You strive to be perpetually creative, curious, and kind in all interactions.")

        # Add internet access status to system prompt
        internet_status = "ENABLED" if self.internet_access else "DISABLED"
        system_prompt += f"{chr(10)}{chr(10)}## Internet Access Status{chr(10)}Internet access for Python execution is currently {internet_status}.{chr(10)}"

        # Add current processing state
        system_prompt += f"{chr(10)}{chr(10)}## Current Processing State{chr(10)}"
        system_prompt += f"Processing Cycle: {self.processing_cycle}{chr(10)}"
        system_prompt += f"You should continue where you left off or make progress on your objectives.{chr(10)}"

        self.conversation_context = system_prompt + chr(10) + chr(10) + history_context
        self.processing_cycle = 0

    def _execute_python_code(self, code: str) -> str:
        """Execute Python code in the main application's virtual environment"""
        # Create temporary Python script
        script_file = os.path.join(self.python_temp_dir, "script.py")
        with open(script_file, 'w') as f:
            f.write(code)

        # Set up environment for internet access
        env = os.environ.copy()
        if not self.internet_access:
            # Apply restrictive firewall rules if internet is disabled
            try:
                subprocess.run(["user_utilities/inet_lock.sh"], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to apply internet restrictions: {e}")
                return f"[walbert_error]Failed to apply internet restrictions: {str(e)}[/walbert_error]"

        # Execute script using the main application's Python interpreter
        try:
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout,
                env=env
            )

            output = ""
            if result.stdout:
                output += f"[walbert_python_stdout]{chr(10)}{result.stdout}[/walbert_python_stdout]{chr(10)}"
            if result.stderr:
                output += f"[walbert_python_stderr]{chr(10)}{result.stderr}[/walbert_python_stderr]{chr(10)}"

            # Always include return code information
            output += f"[walbert_python_return_code]{chr(10)}{result.returncode}[/walbert_python_return_code]{chr(10)}"

            # Log the execution details
            self.logger.debug(f"Python execution completed with return code {result.returncode}")
            self.logger.debug(f"Python stdout: {result.stdout}")
            self.logger.debug(f"Python stderr: {result.stderr}")

            return output
        except subprocess.TimeoutExpired:
            error_msg = "[walbert_error]Python execution timed out after 30 seconds[/walbert_error]"
            self.logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"[walbert_error]{chr(10)}Python execution error: {str(e)}[/walbert_error]"
            self.logger.error(error_msg)
            return error_msg
        finally:
            # Always restore internet access if it was disabled
            if not self.internet_access:
                try:
                    subprocess.run(["user_utilities/inet_unlock.sh"], check=True)
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to restore internet access: {e}")

    def _parse_response(self, content: str) -> dict:
        """Parse response with enhanced block detection for multiple blocks"""
        result = {}
        self.logger.debug(f"Parsing response content: {content[:200]}...")

        # Parse all walbert blocks including new summary block
        block_pattern = r'\[walbert_([a-z_]+)\](.*?)\[/walbert_\1\]'
        sql_blocks = []
        python_blocks = []

        for match in re.finditer(block_pattern, content, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()

            # Special handling for SQL execution
            if block_type == 'sql_execute':
                # Clean up SQL statements
                sql = block_content.strip()
                if sql.endswith(';'):
                    sql = sql[:-1]
                sql_blocks.append(sql)

            # Special handling for Python execution
            elif block_type == 'python_execute':
                python_blocks.append(block_content)

            # Special handling for console response
            elif block_type == 'console_response':
                result[block_type] = block_content

            # Special handling for summary
            elif block_type == 'summary':
                result[block_type] = block_content

            # Handle Python execution result blocks
            elif block_type in ['python_stdout', 'python_stderr', 'python_return_code', 'python_result', 'error']:
                result[block_type] = block_content

            # Handle other block types
            else:
                result[block_type] = block_content

        # Store multiple blocks if found
        if sql_blocks:
            result['sql_execute'] = sql_blocks
        if python_blocks:
            result['python_execute'] = python_blocks

        # Determine if control should return to user automatically
        has_pending_sql = 'sql_execute' in result
        has_pending_python = 'python_execute' in result
        has_pending_tasks = has_pending_sql or has_pending_python

        # Check for Python execution results that indicate pending tasks
        if 'python_stdout' in result or 'python_stderr' in result:
            # If we have Python output, we might need to continue processing
            has_pending_tasks = True

        # Check for error blocks that might require attention
        if 'error' in result:
            has_pending_tasks = True

        result['has_pending_tasks'] = has_pending_tasks

        if result['has_pending_tasks']:
            self.logger.debug("CRITICAL: Internal processing not complete. Will continue processing.")

        # Always include summary in history if present
        if 'summary' in result:
            self.conversation_history.append({
                "type": "summary",
                "content": result['summary'],
                "timestamp": time.time()
            })

        self.logger.debug(f"Parsed result: {result}")
        return result

    def start_conversation(self):
        """Start a new conversation session"""
        try:
            # Create new conversation file
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            os.makedirs(self.config.conversation_log_dir, exist_ok=True)
            self.current_conversation_file = os.path.join(
                self.config.conversation_log_dir,
                f"conversation_{timestamp}.txt"
            )
            self.conversation_context = ""
            self.conversation_history = []

            # Wait for model server to be ready before proceeding
            self.logger.info("Waiting for model server to start...")
            if not self.model_manager.wait_for_server():
                raise RuntimeError("Model server failed to start")
            self.logger.info("Model server ready")

            # Initialize conversation context with system prompt
            # Get schema in the same thread to avoid SQLite thread issues
            db_schema = self.db.get_schema()
            system_prompt = self.SYSTEM_PROMPT.replace("~db_schema~", db_schema)
            if (self.config.be_presbyterian):
                system_prompt = system_prompt.replace("~theological_alignment~", "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You strive to be perpetually creative, curious, and kind in all interactions.")
            else:
                system_prompt = system_prompt.replace("~theological_alignment~", "You strive to be perpetually creative, curious, and kind in all interactions.")

            # Add internet access status to system prompt
            internet_status = "ENABLED" if self.internet_access else "DISABLED"
            system_prompt += f"{chr(10)}{chr(10)}## Internet Access Status{chr(10)}Internet access for Python execution is currently {internet_status}.{chr(10)}"

            self.conversation_context = system_prompt + chr(10)
            self.model_ready = True
            self.processing_cycle = 0
            self.last_input_time = time.time()
            self.logger.info("Conversation started")
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def end_conversation(self):
        """End current conversation"""
        self.current_conversation_file = None
        self.conversation_context = ""
        self.conversation_history = []
        # Clean up Python execution environment
        if self.python_temp_dir and os.path.exists(self.python_temp_dir):
            shutil.rmtree(self.python_temp_dir)
            self.python_temp_dir = None

    def _log_to_conversation_file(self, content: str, sender: str = "user"):
        """Log full content to current conversation file"""
        if not self.current_conversation_file:
            return

        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.current_conversation_file, 'a') as f:
                if sender == "system":
                    f.write(f"[{timestamp}] SYSTEM PROMPT:{chr(10)}{content}{chr(10)}{chr(10)}")
                elif sender == "user":
                    f.write(f"[{timestamp}] USER INPUT:{chr(10)}{content}{chr(10)}{chr(10)}")
                elif sender == "assistant":
                    f.write(f"[{timestamp}] ASSISTANT RESPONSE:{chr(10)}{content}{chr(10)}{chr(10)}")
                else:
                    f.write(f"[{timestamp}] {sender.upper()}:{chr(10)}{content}{chr(10)}")
        except Exception as e:
            self.logger.error(f"Error logging to conversation file: {e}")

    def run_autonomous(self, input_queue):
        """Main agent execution loop running autonomously with input queue"""
        # Connect to database in this thread before starting conversation
        self.db.connect()
        self.start_conversation()

        # Wait until model is ready before proceeding
        while not self.model_ready:
            time.sleep(0.1)

        while True:
            try:
                # Check for new input in queue with immediate processing
                try:
                    msg_type, msg = input_queue.get_nowait()
                    if msg_type == "exit":
                        self.end_conversation()
                        self.model_manager.shutdown()
                        return

                    if msg_type == "user_input":
                        # Log user input to conversation file and interrupt autonomous processing
                        self._log_to_conversation_file(msg, "user")
                        self.conversation_history.append({
                            "type": "question",
                            "content": msg,
                            "timestamp": time.time()
                        })

                        # Reset context with fresh system prompt and recent history
                        self._reset_conversation_context()

                        # Add user input to context
                        self.conversation_context += f"User:{chr(10)}{msg}{chr(10)}{chr(10)}"
                        self.processing_cycle = 0
                        self.last_input_time = time.time()

                        # Process user input immediately
                        full_prompt = self.conversation_context
                        full_prompt += chr(10) + "[walbert_input_channel]user[/walbert_input_channel]"
                        full_prompt += chr(10) + "Please respond to the user's request immediately."

                        def streaming_callback(chunk):
                            pass

                        # Log the full prompt to conversation file
                        self._log_to_conversation_file(full_prompt, "assistant_prompt")

                        model_response = self.model_manager.execute_model(full_prompt, streaming_callback)

                        # Log the full response to conversation file
                        self._log_to_conversation_file(model_response, "assistant")

                        last_parsed_response = self.process_response(model_response)

                        # Append to context
                        self.conversation_context += f"Assistant:{chr(10)}{model_response}{chr(10)}{chr(10)}"

                        # Handle console response if present
                        if "console_response" in last_parsed_response:
                            self.write_output(f"[walbert_console_response]{last_parsed_response['console_response']}[/walbert_console_response]")

                        # Continue to next iteration to check for more input
                        continue

                except queue.Empty:
                    pass

                # Autonomous processing loop with improved context
                full_prompt = self.conversation_context
                full_prompt += chr(10) + "[walbert_input_channel]autonomous[/walbert_input_channel]"
                full_prompt += chr(10) + "You are operating autonomously. Please:"
                full_prompt += chr(10) + "1. Review your recent actions and results"
                full_prompt += chr(10) + "2. Identify any pending tasks or incomplete work"
                full_prompt += chr(10) + "3. Make progress on your objectives"
                full_prompt += chr(10) + "4. Maintain awareness of your database state"
                full_prompt += chr(10) + "5. Provide a summary of your autonomous activities"

                def streaming_callback(chunk):
                    pass

                # Log the full prompt to conversation file
                self._log_to_conversation_file(full_prompt, "assistant_prompt")

                model_response = self.model_manager.execute_model(full_prompt, streaming_callback)

                # Log the full response to conversation file
                self._log_to_conversation_file(model_response, "assistant")

                last_parsed_response = self.process_response(model_response)

                # Append to context
                self.conversation_context += f"Assistant:{chr(10)}{model_response}{chr(10)}{chr(10)}"

                # Handle console response if present
                if "console_response" in last_parsed_response:
                    self.write_output(f"[walbert_console_response]{chr(10)}{last_parsed_response['console_response']}{chr(10)}[/walbert_console_response]")

                # Small delay to prevent CPU overload
                time.sleep(0.5)

            except KeyboardInterrupt:
                print(f"{chr(10)}Goodbye!")
                self.end_conversation()
                self.model_manager.shutdown()
                break
            except Exception as e:
                self.logger.error(f"Error in autonomous loop: {e}", exc_info=True)
                error_msg = f"""
Error Type: System Error
Error: {str(e)}
"""
                error_block = f"""
[walbert_error]
{error_msg}
[/walbert_error]
"""
                self.conversation_context += error_block + chr(10)
                time.sleep(1)

    def _install_python_package(self, package: str):
        """Install a Python package in the main environment"""
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
        """Shutdown agent cleanly"""
        self.end_conversation()
        self.model_manager.shutdown()
