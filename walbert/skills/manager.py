"""
Skill manager implementation
"""

import tempfile
import subprocess
import os
import logging

logger = logging.getLogger('walbert.skills')

class SkillManager:
    """Manages skill execution"""
    def __init__(self, db):
        self.db = db

    def execute_skill(self, skill_code: str) -> str:
        """Execute a skill in sandboxed environment"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(skill_code)
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                ['python3', temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "Unknown error"
                logger.error(f"Skill execution failed: {error_msg}")
                return f"Error: {error_msg}"
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("Skill execution timed out")
            return "Error: Skill execution timed out"
        except Exception as e:
            logger.error(f"Skill execution error: {e}")
            return f"Error: {str(e)}"
        finally:
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")
