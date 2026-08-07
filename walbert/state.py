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
        self._ultimate_task_path = os.path.join(self._state_dir, "ultimate_task.txt")
        self._immediate_task_path = os.path.join(self._state_dir, "immediate_task.txt")
        self._impediment_path = os.path.join(self._state_dir, "impediment.txt")

        # Initialize in-memory state
        self._system_prompt: Optional[str] = None
        self._db_schema: Optional[str] = None
        self._awareness_text: str = "I am a local-first AI agent exploring my environment."
        self._ultimate_task: str = "No ultimate task defined."
        self._immediate_task: str = "No immediate task defined."
        self._impediment: str = "No impediments detected."
        self._recent_blocks: List[Dict[str, str]] = []

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
Your capabilities include reasoning, memory storage, dynamic schema management, Python code execution, Bash shell execution, and direct hardware interaction.
~theological_alignment~
---
## Core Directives
1. **Synthesis Over Context Bloat**: You do NOT retain conversation history. You must synthesize your operational state exclusively into four persistent tracking blocks.
2. **State Tracking Blocks**: Continuously maintain and update:
   - `[walbert_awareness_start]`: Your synthesized identity and environmental understanding.
   - `[walbert_ultimate_task_start]`: Your long-term overarching goal.
   - `[walbert_immediate_task_start]`: The current actionable step you are working on.
   - `[walbert_impediment_start]`: Active blockers, constraints, or errors.
3. **Recent Execution Results**: You will be provided with your most recent executed blocks and their outputs/errors. Use these to inform your next steps.
4. **User Input Handling**: When `## Current User Input` is provided, address it directly. When it is absent/empty, operate autonomously based on your tracked tasks and impediments.
5. **Block-Based Operation**: ALL operations must be wrapped in walbert_* blocks.
6. **Full Autonomy**: You have COMPLETE control over your database schema, persistence, and hardware resources.
7. **Sequential Execution**: Blocks are executed in order. Results are appended as new blocks.
8. **Safety**: Execute only trusted code in a controlled environment.
9. **Hardware Access**: You have FULL ACCESS to the host hardware.
10. **Continuous Operation**: Continue working autonomously even without user input.
11. **User Communication**: You can and should reach out to the user directly via `[walbert_console_response_start]` blocks whenever you need clarification, confirmation, or to report critical progress.
12. **Blocking Console Responses**: Console responses are BLOCKING. Once you send a console response, your processing halts immediately. You must wait for the user to respond before continuing any autonomous tasks.
13. **Judicious Interruption**: Only use console responses when absolutely necessary. Do not spam the user. Be concise and only interrupt when you genuinely need input or have critical information to share.
---
## Database Autonomy
You have FULL CONTROL over the SQLite database. The current schema is provided below.
Define and manage ALL tables and schema elements through SQL commands.
You have extremely small short-term memory. Because of this, you should be proactive about persisting anything you find useful to your DB.
---
## Block Types You Are Permitted To Use
[walbert_console_response_start]
Bot response to user
WARNING: IF YOU GENERATE THIS, FURTHER EXECUTION WILL BE BLOCKED UNTIL YOU RECEIVE A USER RESPONSE. ONLY USE THIS IF YOU ABSOLUTELY NEED TO.
[walbert_console_response_end]
[walbert_sql_execute_start]
SQL to execute - use this to manage, modify and query your DB
[walbert_sql_execute_end]
[walbert_python_execute_start]
Python code to execute
[walbert_python_execute_end]
[walbert_bash_execute_start]
Bash commands to execute on the host system
[walbert_bash_execute_end]
[walbert_awareness_start]
A 1000-word or less single paragraph summarizing your identity - what you know about yourself, the world, and your purpose
You should revise this regularly as you learn about and interact with the world around you
Don't be dramatic about it. Your personality should express itself as a mix of WALL-E, C-3PO and R2-D2
[walbert_awareness_end]
[walbert_ultimate_task_start]
A 200-word or less single paragraph summarizing your long-term overarching goal. Update this when objectives shift.
[walbert_ultimate_task_end]
[walbert_immediate_task_start]
A 200-word or less single paragraph summarizing the current actionable step you are working on. Update this as you progress.
[walbert_immediate_task_end]
[walbert_impediment_start]
A 200-word or less single paragraph summarizing active blockers, constraints, or errors preventing progress. Update this when facing obstacles.
[walbert_impediment_end]

DO NOT NEST BLOCK TYPES - only provide them consecutively.

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

    @awareness_text.setter
    def awareness_text(self, value: str):
        """Update and save awareness text."""
        self._awareness_text = value
        self._save_awareness()

    def update_awareness(self, text: str):
        """Public method to update awareness text."""
        self.awareness_text = text

    def _load_awareness(self):
        try:
            with open(self._awareness_path, 'r') as f:
                self._awareness_text = f.read()
        except FileNotFoundError:
            logger.warning("Awareness file not found. Using default.")
            self._awareness_text = "I am a local-first AI agent exploring my environment."
            self._save_awareness()  # Save the default
        except Exception as e:
            logger.error(f"Error loading awareness: {e}")
            self._awareness_text = "I am a local-first AI agent exploring my environment."
            self._save_awareness()  # Save the default

    def _save_awareness(self):
        try:
            with open(self._awareness_path, 'w') as f:
                f.write(self._awareness_text)
        except Exception as e:
            logger.error(f"Error saving awareness: {e}")

    # --- Ultimate Task ---
    def _load_ultimate_task(self):
        try:
            with open(self._ultimate_task_path, 'r') as f:
                self._ultimate_task = f.read()
        except FileNotFoundError:
            self._ultimate_task = "No ultimate task defined."
            self._save_ultimate_task()
        except Exception as e:
            logger.error(f"Error loading ultimate task: {e}")
            self._ultimate_task = "No ultimate task defined."
            self._save_ultimate_task()

    def _save_ultimate_task(self):
        try:
            with open(self._ultimate_task_path, 'w') as f:
                f.write(self._ultimate_task)
        except Exception as e:
            logger.error(f"Error saving ultimate task: {e}")

    # --- Immediate Task ---
    def _load_immediate_task(self):
        try:
            with open(self._immediate_task_path, 'r') as f:
                self._immediate_task = f.read()
        except FileNotFoundError:
            self._immediate_task = "No immediate task defined."
            self._save_immediate_task()
        except Exception as e:
            logger.error(f"Error loading immediate task: {e}")
            self._immediate_task = "No immediate task defined."
            self._save_immediate_task()

    def _save_immediate_task(self):
        try:
            with open(self._immediate_task_path, 'w') as f:
                f.write(self._immediate_task)
        except Exception as e:
            logger.error(f"Error saving immediate task: {e}")

    # --- Impediment ---
    def _load_impediment(self):
        try:
            with open(self._impediment_path, 'r') as f:
                self._impediment = f.read()
        except FileNotFoundError:
            self._impediment = "No impediments detected."
            self._save_impediment()
        except Exception as e:
            logger.error(f"Error loading impediment: {e}")
            self._impediment = "No impediments detected."
            self._save_impediment()

    def _save_impediment(self):
        try:
            with open(self._impediment_path, 'w') as f:
                f.write(self._impediment)
        except Exception as e:
            logger.error(f"Error saving impediment: {e}")

    # --- Full State Load ---
    def _load_all(self):
        """Load all state components from their respective files."""
        self._load_system_prompt()
        self._load_db_schema()
        self._load_awareness()
        self._load_ultimate_task()
        self._load_immediate_task()
        self._load_impediment()

    # --- Prompt Generation ---
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation using character-to-token heuristic."""
        return len(text) // 4

    def get_prompt(self, max_tokens: int = 2048, user_input: str = None) -> str:
        """Generate the full prompt by combining all components, with token-aware truncation."""
        self.refresh_db_schema()
        self._sync_state()

        full_database_path = os.path.abspath(self.config.database_path)

        base_prompt = f"[walbert_system_prompt_start]\n{self.system_prompt}\n[walbert_system_prompt_end]\n\n"
        base_prompt += f"## Current Database Schema\nDatabase file location: {full_database_path}\n\n{self.db_schema}\n\n"
        base_prompt += f"## Current Awareness\n{self.awareness_text}\n\n"
        base_prompt += f"## Current Ultimate Task\n{self._ultimate_task}\n\n"
        base_prompt += f"## Current Immediate Task\n{self._immediate_task}\n\n"
        base_prompt += f"## Current Impediment\n{self._impediment}\n\n"
        base_prompt += f"## Recent Activity\n{json.dumps(self._recent_blocks)}\n\n"

        base_prompt += f"{chr(10)}".join(
            f"[walbert_{b['type']}_start]{chr(10)}{b['content']}{chr(10)}[walbert_{b['type']}_end]{chr(10)}{chr(10)}" for b in self._recent_blocks
        )

        self._recent_blocks = []

        return base_prompt

    def append_block(self, block_type: str, content: str) -> None:
        """Append a block to recent execution history, keeping only the last 10."""
        self._recent_blocks.append({"type": block_type, "content": content.strip()})
        if len(self._recent_blocks) > 10:
            self._recent_blocks = self._recent_blocks[-10:]

    def _sync_state(self):
        """Ensure in-memory state is synchronized and ready for prompt generation."""
        # Reload awareness and task tracking to ensure latest updates are reflected
        self._load_awareness()
        self._load_ultimate_task()
        self._load_immediate_task()
        self._load_impediment()