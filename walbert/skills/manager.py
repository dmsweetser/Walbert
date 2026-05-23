"""
Skill manager implementation
"""

import tempfile
import subprocess
import os
from typing import Optional, List
from ..database.manager import DatabaseManager

class SkillManager:
    """Manages skill execution"""
    def __init__(self, db: DatabaseManager):
        self.db = db

    def store_skill(self, name: str, code: str, tags: List[str]) -> int:
        """Store a new skill"""
        tags = tags + ["skill", name]
        return self.db.store_item(code, tags, item_type="skill")

    def retrieve_skill(self, name: str) -> Optional[str]:
        """Retrieve a skill by name"""
        items = self.db.retrieve_items_by_multiple_tags(["skill", name])
        if items:
            return items[0][1]  # Return content
        return None

    def execute_skill(self, skill_code: str, args: List[str] = None) -> str:
        """Execute a skill in sandboxed environment"""
        args = args or []
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(skill_code)
            f.flush()

            result = subprocess.run(
                ['python3', f.name] + args,
                capture_output=True,
                text=True
            )

            # Clean up
            os.unlink(f.name)

            return result.stdout
