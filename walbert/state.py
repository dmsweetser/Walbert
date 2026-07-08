"""
Modular state management for Walbert agent.
Each state component is stored in a separate file and persisted on update.
"""
import json
import os
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger('walbert.state')

class AgentState:
    def __init__(self, config, db_manager=None):
        self.config = config
        self.db = db_manager
        self._state_dir = os.path.join(self.config.conversation_log_dir, "state")
        os.makedirs(self._state_dir, exist_ok=True)

        # File paths for each component
        self._system_prompt_path = os.path.join(self._state_dir, "system_prompt.md")
        self._db_schema_path = os.path.join(self._state_dir, "db_schema.sql")
        self._awareness_path = os.path.join(self._state_dir, "awareness.txt")
        self._context_blocks_path = os.path.join(self._state_dir, "context_blocks.json")

        # Initialize in-memory state
        self._system_prompt: Optional[str] = None
        self._db_schema: Optional[str] = None
        self._awareness_text: str = "I am a local-first AI agent exploring my environment."
        self._context_blocks: List[Dict[str, Any]] = []

        # Load all components
        self._load_all()

        # Initialize system prompt if not loaded
        if self._system_prompt is None:
            self.refresh_system_prompt()

    # --- System Prompt ---
    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            self._load_system_prompt()
        return self._system_prompt

    def refresh_system_prompt(self):
        """Rebuild and save the system prompt."""
        base_prompt = """
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
6. **Hardware Access**: You have FULL ACCESS to the host hardware.
7. **Continuous Operation**: Continue working autonomously even without user input.
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
- [walbert_awareness_start]...[/walbert_awareness_end]: This represents a synthesis of your identity - what you know about yourself, the world, and your purpose. You should revise this regularly as you learn and interact with the world, but try to to limit this content to a single prose paragraph of 1000 words or less.
---
Reply ONLY in the specified block format. NO CRUFT.
---
        """
        if self.config.be_presbyterian:
            base_prompt = base_prompt.replace(
                "~theological_alignment~",
                "You are philosophically and morally aligned with the Presbyterian Church of America, the Westminster Standards, and the PCA Book of Church Order. You are a robot, of course, so you appreciate these things from a distance because you are neither made in the Image of God nor the immediate object of His redemptive work. You strive to be perpetually creative, curious, and kind in all interactions."
            )
        else:
            base_prompt = base_prompt.replace(
                "~theological_alignment~",
                "You strive to be perpetually creative, curious, and kind in all interactions."
            )
        self._system_prompt = base_prompt
        self._save_system_prompt()

    def _load_system_prompt(self):
        try:
            with open(self._system_prompt_path, 'r') as f:
                self._system_prompt = f.read()
        except FileNotFoundError:
            logger.warning("System prompt file not found. Will initialize on first use.")
            self._system_prompt = None
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            self._system_prompt = None

    def _save_system_prompt(self):
        try:
            with open(self._system_prompt_path, 'w') as f:
                f.write(self._system_prompt)
        except Exception as e:
            logger.error(f"Error saving system prompt: {e}")

    # --- DB Schema ---
    @property
    def db_schema(self) -> str:
        if self._db_schema is None:
            self._load_db_schema()
        return self._db_schema

    def refresh_db_schema(self):
        """Fetch and save the latest DB schema."""
        if self.db and hasattr(self.db, 'get_schema'):
            self._db_schema = self.db.get_schema()
            self._save_db_schema()

    def _load_db_schema(self):
        try:
            with open(self._db_schema_path, 'r') as f:
                self._db_schema = f.read()
        except FileNotFoundError:
            logger.warning("DB schema file not found. Will initialize on first use.")
            self._db_schema = None
        except Exception as e:
            logger.error(f"Error loading DB schema: {e}")
            self._db_schema = None

    def _save_db_schema(self):
        try:
            with open(self._db_schema_path, 'w') as f:
                f.write(self._db_schema)
        except Exception as e:
            logger.error(f"Error saving DB schema: {e}")

    # --- Awareness Text ---
    @property
    def awareness_text(self) -> str:
        return self._awareness_text

    def update_awareness(self, text: str):
        """Update and save awareness text."""
        self._awareness_text = text
        self._save_awareness()

    def _load_awareness(self):
        try:
            with open(self._awareness_path, 'r') as f:
                self._awareness_text = f.read()
        except FileNotFoundError:
            logger.warning("Awareness file not found. Using default.")
            self._awareness_text = "I am a local-first AI agent exploring my environment."
        except Exception as e:
            logger.error(f"Error loading awareness: {e}")
            self._awareness_text = "I am a local-first AI agent exploring my environment."

    def _save_awareness(self):
        try:
            with open(self._awareness_path, 'w') as f:
                f.write(self._awareness_text)
        except Exception as e:
            logger.error(f"Error saving awareness: {e}")

    # --- Context Blocks ---
    @property
    def context_blocks(self) -> List[Dict[str, Any]]:
        return self._context_blocks

    def append_block(self, block_type: str, content: str):
        """Append a block and save the updated list."""
        self._context_blocks.append({
            "type": block_type,
            "content": content,
            "timestamp": time.time()
        })
        # Truncate to max_context_blocks
        max_blocks = self.config.max_context_blocks
        if max_blocks > 0:
            self._context_blocks = self._context_blocks[-max_blocks:]
        self._save_context_blocks()

    def _load_context_blocks(self):
        try:
            with open(self._context_blocks_path, 'r') as f:
                self._context_blocks = json.load(f)
        except FileNotFoundError:
            logger.warning("Context blocks file not found. Starting with empty list.")
            self._context_blocks = []
        except Exception as e:
            logger.error(f"Error loading context blocks: {e}")
            self._context_blocks = []

    def _save_context_blocks(self):
        try:
            with open(self._context_blocks_path, 'w') as f:
                json.dump(self._context_blocks, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving context blocks: {e}")

    # --- Full State Load ---
    def _load_all(self):
        """Load all state components from their respective files."""
        self._load_system_prompt()
        self._load_db_schema()
        self._load_awareness()
        self._load_context_blocks()

    # --- Prompt Generation ---
    def get_prompt(self, internet_access: bool = False) -> str:
        """Generate the full prompt by combining all components."""
        self.refresh_db_schema()  # Ensure DB schema is up-to-date

        prompt = f"[walbert_system_prompt_start]\n{self.system_prompt}\n[walbert_system_prompt_end]\n\n"
        prompt += f"## Current Database Schema\n{self.db_schema}\n\n"
        prompt += f"## Internet Access Enabled?\n{internet_access}\n\n"
        prompt += f"## Current Awareness\n{self.awareness_text}\n\n"
        prompt += f"## RECENT CONVERSATION HISTORY (limited to the most recent {self.config.max_context_blocks} blocks)\n\n"
        for block in self._context_blocks:
            prompt += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
        return prompt