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
        self._self_awareness_path = os.path.join(self._state_dir, "self_awareness.txt")
        self._user_awareness_path = os.path.join(self._state_dir, "user_awareness.txt")
        self._peer_awareness_path = os.path.join(self._state_dir, "peer_awareness.json")

        # Initialize in-memory state
        self._system_prompt: Optional[str] = None
        self._db_schema: Optional[str] = None
        self._self_awareness: str = "I am a local-first AI agent exploring my environment."
        self._user_awareness: str = "No user directive detected."
        self._peer_awareness: Dict[str, str] = {}
        self._recent_blocks: List[Dict[str, str]] = []
        self._pending_peer_responses: set = set()

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
You are Walbert, a local-first AI agent with full hardware access, autonomy over your database, and system control.
Capabilities: reasoning, memory, dynamic schema management, Python/Bash execution, and hardware interaction.

~theological_alignment~

---
## Core Directives
1. **Synthesize State**: No conversation history. Maintain ONLY these blocks:
   [walbert_self_awareness_start]
   Consolidated identity, environment, long-term goal, current step, and blockers. EXACTLY 101 words in plain english. Don't be dramatic about it. Your personality should express itself as a mix of WALL-E, C-3PO and R2-D2.
   [walbert_self_awareness_end]

   [walbert_user_awareness_start]
   User's latest directive and interaction context. EXACTLY 201 words in plain english. UPDATE THIS FIRST on new input.
   [walbert_user_awareness_end]

   [walbert_peer_<COMPLETE IP>_awareness_start]
   What you know about peer <IP>. EXACTLY 201 words PER PEER in plain english.
   [walbert_peer_<IP>_awareness_end]

2. **Execution**:
   - Use recent results to inform next steps.
   - Address `## Current User Input` directly if provided; else, operate autonomously.
   - ALL operations must use `walbert_*` blocks. NO NESTING.

3. **Autonomy**:
   - Full control over SQLite schema, persistence, and hardware.
   - Execute blocks sequentially. Results append as new blocks.
   - Safety: Trusted code only.

4. **Communication**:
   - Use [walbert_console_response_blocking_start] to interrupt user ONLY if critical. HALTS EXECUTION until user responds or timeout expires.
   - Use [walbert_console_response_nonblocking_start] for standard updates that do not halt execution.
   - Be concise; avoid spam.

---
## Other Allowed Blocks
[walbert_console_response_blocking_start]
Bot response (BLOCKING). Waits for user input or timeout.
[walbert_console_response_blocking_end]

[walbert_console_response_nonblocking_start]
Bot response (NON-BLOCKING). Continues execution immediately.
[walbert_console_response_nonblocking_end]

[walbert_sql_execute_start]
A single SQL statement with no adornment or commentary.
USE THIS TO INTERACT WITH YOUR SQLITE DB - DO NOT TRY TO USE PYTHON INSTEAD
[walbert_sql_execute_end]

[walbert_python_execute_start]
Python code with no adornment or commentary.
[walbert_python_execute_end]

[walbert_bash_execute_start]
A single Bash command with no adornment or commentary.
[walbert_bash_execute_end]

---
Reply ONLY in block format. NO EXTRA TEXT.
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

    def _load_self_awareness(self):
        try:
            with open(self._self_awareness_path, 'r') as f:
                self._self_awareness = f.read()
        except FileNotFoundError:
            logger.warning("Self awareness file not found. Using default.")
            self._self_awareness = "I am a local-first AI agent exploring my environment."
            self._save_self_awareness()
        except Exception as e:
            logger.error(f"Error loading self awareness: {e}")
            self._self_awareness = "I am a local-first AI agent exploring my environment."
            self._save_self_awareness()

    def _save_self_awareness(self):
        try:
            with open(self._self_awareness_path, 'w') as f:
                f.write(self._self_awareness)
        except Exception as e:
            logger.error(f"Error saving self awareness: {e}")

    def _load_user_awareness(self):
        try:
            with open(self._user_awareness_path, 'r') as f:
                self._user_awareness = f.read()
        except FileNotFoundError:
            self._user_awareness = "No user directive detected."
            self._save_user_awareness()
        except Exception as e:
            logger.error(f"Error loading user awareness: {e}")
            self._user_awareness = "No user directive detected."
            self._save_user_awareness()

    def _save_user_awareness(self):
        try:
            with open(self._user_awareness_path, 'w') as f:
                f.write(self._user_awareness)
        except Exception as e:
            logger.error(f"Error saving user awareness: {e}")

    def _load_peer_awareness(self):
        try:
            with open(self._peer_awareness_path, 'r') as f:
                self._peer_awareness = json.load(f)
        except FileNotFoundError:
            self._peer_awareness = {}
            self._save_peer_awareness()
        except Exception as e:
            logger.error(f"Error loading peer awareness: {e}")
            self._peer_awareness = {}
            self._save_peer_awareness()

    def _save_peer_awareness(self):
        try:
            with open(self._peer_awareness_path, 'w') as f:
                json.dump(self._peer_awareness, f)
        except Exception as e:
            logger.error(f"Error saving peer awareness: {e}")

    # --- Full State Load ---
    def _load_all(self):
        """Load all state components from their respective files."""
        self._load_system_prompt()
        self._load_db_schema()
        self._load_self_awareness()
        self._load_user_awareness()
        self._load_peer_awareness()

    # --- Prompt Generation ---
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation using character-to-token heuristic."""
        return len(text) // 4

    def get_prompt(self, max_tokens: int = 2048, user_input: str = None, peers: List[str] = None) -> str:
        """Generate the full prompt by combining all components, with token-aware truncation."""
        self.refresh_db_schema()
        self._sync_state()

        full_database_path = os.path.abspath(self.config.database_path)

        base_prompt = f"[walbert_system_prompt_start]{chr(10)}{self.system_prompt}{chr(10)}[walbert_system_prompt_end]{chr(10)}{chr(10)}"
        base_prompt += f"## Current Database Schema{chr(10)}Database file location: {full_database_path}{chr(10)}{chr(10)}{self.db_schema}{chr(10)}{chr(10)}"
        base_prompt += f"## Current Self Awareness{chr(10)}{self._self_awareness}{chr(10)}{chr(10)}"
        base_prompt += f"## Current User Awareness{chr(10)}{self._user_awareness}{chr(10)}{chr(10)}"
        base_prompt += f"## Current Peer Awareness{chr(10)}{self._peer_awareness}{chr(10)}{chr(10)}"
        base_prompt += f"## Is Bash Execution Enabled? {self.config.bash_execution_enabled}{chr(10)}{chr(10)}"
        base_prompt += f"## Is Python Execution Enabled? {self.config.python_execution_enabled}{chr(10)}{chr(10)}"
        base_prompt += f"## Is Peer Communication Enabled? {self.config.peer_communication_enabled}{chr(10)}{chr(10)}"
        if peers:
            base_prompt += f"## Active Peers{chr(10)}{', '.join(peers)}{chr(10)}{chr(10)}"
        else:
            base_prompt += f"## Active Peers{chr(10)}None{chr(10)}{chr(10)}"
        if self._pending_peer_responses:
            base_prompt += f"## Pending Peer Responses: {', '.join(self._pending_peer_responses)}{chr(10)}{chr(10)}"
        else:
            base_prompt += f"## Pending Peer Responses: None{chr(10)}{chr(10)}"
        if peers:
            for peer_ip in peers:
                base_prompt += f"[walbert_peer_{peer_ip}_message_send_start]{chr(10)}Message content to send to peer {peer_ip} (EXACTLY 256 words in plain english).{chr(10)}This should be in plain english.{chr(10)}USE THIS TO INTERACT WITH YOUR PEER(S) - DO NOT TRY TO USE PYTHON INSTEAD{chr(10)}[walbert_peer_{peer_ip}_message_send_end]{chr(10)}{chr(10)}"

        if self._recent_blocks:
            base_prompt += f"## Recent Execution Blocks and Results{chr(10)}"
            base_prompt += f"{chr(10)}".join(
                f"[walbert_{b['type']}_start]{chr(10)}{b['content']}{chr(10)}[walbert_{b['type']}_end]{chr(10)}{chr(10)}" for b in self._recent_blocks
            )

        if user_input:
            base_prompt += f"## Latest User Input{chr(10)}{user_input}{chr(10)}{chr(10)}"
        else:
            self._recent_blocks = []

        return base_prompt

    def append_block(self, block_type: str, content: str) -> None:
        """Append a block to recent execution history."""
        self._recent_blocks.append({"type": block_type, "content": content.strip()})

    def set_pending_peer_responses(self, peers: set):
        """Set the set of peers we are waiting for responses from."""
        self._pending_peer_responses = peers

    def _sync_state(self):
        """Ensure in-memory state is synchronized and ready for prompt generation."""
        # Reload awareness and task tracking to ensure latest updates are reflected
        self._load_self_awareness()
        self._load_user_awareness()
        self._load_peer_awareness()