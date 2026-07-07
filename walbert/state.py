"""
Centralized state management for Walbert agent
"""
import json
import os
import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger('walbert.state')

class AgentState:
    def __init__(self, config, db_manager):
        self.config = config
        self.db = db_manager
        self.context_blocks: List[Dict[str, Any]] = []
        self.system_prompt: str = ""
        self.awareness_text: str = "I am a local-first AI agent exploring my environment."
        self.context_json_path = os.path.join(self.config.conversation_log_dir, "context_cache.json")
        self.awareness_json_path = os.path.join(self.config.conversation_log_dir, "awareness_cache.json")

        self._load_context_from_json()
        self._load_awareness_from_json()
        self.refresh_system_prompt()

    def refresh_system_prompt(self):
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
- [walbert_awareness_start]...[/walbert_awareness_end]: This represents a synthesis of your identity - what you know about yourself, the world, and your purpose. You should revise this regularly as you learn and interact with the world, but try to to limit this content to 1000 words or less.
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
        self.system_prompt = base_prompt
        self.save_to_json()

    def append_block(self, block_type: str, content: str):
        self.context_blocks.append({
            "type": block_type,
            "content": content,
            "timestamp": time.time()
        })
        other_blocks = [b for b in self.context_blocks if b["type"] != "system_prompt"]
        max_other = self.config.max_context_blocks - 1
        if max_other > 0:
            other_blocks = other_blocks[-max_other:]
        else:
            other_blocks = []
        self.context_blocks = [{"type": "system_prompt", "content": self.system_prompt, "timestamp": time.time()}] + other_blocks
        self.save_to_json()

    def get_prompt(self, internet_access: bool = False) -> str:
        prompt = f"[walbert_system_prompt_start]\n{self.system_prompt}\n[walbert_system_prompt_end]\n\n"
        current_schema = self.db.get_schema()
        prompt += f"## Current Database Schema\n{current_schema}\n\n"
        prompt += f"## Current Awareness\n{self.awareness_text}\n\n"
        prompt += f"## RECENT CONVERSATION HISTORY (limited to the most recent {self.config.max_context_blocks} blocks)\n\n"
        for block in self.context_blocks:
            if block["type"] == "system_prompt":
                continue
            prompt += f"[walbert_{block['type']}_start]\n{block['content']}\n[walbert_{block['type']}_end]\n\n"
        return prompt

    def save_to_json(self):
        try:
            os.makedirs(os.path.dirname(self.context_json_path), exist_ok=True)
            with open(self.context_json_path, 'w') as f:
                json.dump({
                    "context_blocks": self.context_blocks,
                    "awareness": self.awareness_text,
                    "system_prompt": self.system_prompt
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state cache: {e}")

    def _load_context_from_json(self):
        try:
            if os.path.exists(self.context_json_path):
                with open(self.context_json_path, 'r') as f:
                    data = json.load(f)
                    self.context_blocks = data.get("context_blocks", [])
                    self.awareness_text = data.get("awareness", self.awareness_text)
                    self.system_prompt = data.get("system_prompt", self.system_prompt)
                    logger.info(f"Loaded {len(self.context_blocks)} context blocks from cache.")
                    return True
        except Exception as e:
            logger.error(f"Error loading state cache: {e}")
        return False

    def _load_awareness_from_json(self):
        try:
            if os.path.exists(self.awareness_json_path):
                with open(self.awareness_json_path, 'r') as f:
                    data = json.load(f)
                    self.awareness_text = data.get("awareness", self.awareness_text)
                    logger.info("Loaded awareness from cache.")
        except Exception as e:
            logger.error(f"Error loading awareness cache: {e}")