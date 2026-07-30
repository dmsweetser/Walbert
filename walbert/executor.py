"""
Block execution logic for Walbert agent
"""
import os
import sys
import tempfile
import subprocess
import shutil
import logging
from typing import Dict, Optional

logger = logging.getLogger('walbert.executor')

class BlockExecutor:
    def __init__(self, config, db_manager, internet_access: bool = False):
        self.config = config
        self.db = db_manager
        self.internet_access = internet_access
        self.python_temp_dir = None

    def execute(self, block: Dict[str, str]) -> Optional[Dict[str, str]]:
        block_type = block["type"]
        content = block["content"]

        if block_type == "sql_execute":
            return self._execute_sql(content)
        elif block_type == "python_execute":
            return self._execute_python(content)
        elif block_type == "bash_execute":
            return self._execute_bash(content)
        elif block_type == "console_response":
            return {"type": "console_response", "content": f"Walbert:\n{content}\n"}
        elif block_type == "awareness":
            return {"type": "awareness_update", "content": content}
        return None

    def _execute_sql(self, sql: str) -> Dict[str, str]:
        try:
            if not self._is_sql_safe(sql):
                return {"type": "sql_result", "content": "SQL execution error: Unsafe SQL statement detected."}
            result = self.db.execute_sql(sql)
            return {"type": "sql_result", "content": f"{result}\n"}
        except Exception as e:
            return {"type": "sql_result", "content": f"SQL execution error: {str(e)}"}

    def _execute_python(self, code: str) -> Dict[str, str]:
        if not self.config.python_execution_enabled:
            return {"type": "python_result", "content": "Python execution is disabled."}
        try:
            if not self.python_temp_dir:
                self.python_temp_dir = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)
            script_file = os.path.join(self.python_temp_dir, "script.py")
            with open(script_file, 'w') as f:
                f.write(code)

            python_cmd = [sys.executable, script_file]

            result = subprocess.run(
                python_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout,
                env=os.environ.copy(),
                cwd=self.python_temp_dir
            )
            output_parts = []
            if result.stdout:
                output_parts.append(f"Python stdout:\n{result.stdout.strip()}")
            if result.stderr:
                output_parts.append(f"Python stderr:\n{result.stderr.strip()}")
            output_parts.append(f"Python return code: {result.returncode}")
            return {"type": "python_result", "content": f"{chr(10)}".join(output_parts) + f"{chr(10)}"}
        except subprocess.TimeoutExpired:
            return {"type": "python_result", "content": f"Python execution timed out after {self.config.python_execution_timeout} seconds"}
        except Exception as e:
            return {"type": "python_result", "content": f"Python execution error: {str(e)}"}

    def _execute_bash(self, code: str) -> Dict[str, str]:
        if not self.config.bash_execution_enabled:
            return {"type": "bash_result", "content": "Bash execution is disabled."}
        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout,
                env=os.environ.copy()
            )
            output_parts = []
            if result.stdout:
                output_parts.append(f"Bash stdout:\n{result.stdout.strip()}")
            if result.stderr:
                output_parts.append(f"Bash stderr:\n{result.stderr.strip()}")
            output_parts.append(f"Bash return code: {result.returncode}")
            return {"type": "bash_result", "content": f"{chr(10)}".join(output_parts) + f"{chr(10)}"}
        except subprocess.TimeoutExpired:
            return {"type": "bash_result", "content": f"Bash execution timed out after {self.config.python_execution_timeout} seconds"}
        except Exception as e:
            return {"type": "bash_result", "content": f"Bash execution error: {str(e)}"}
            
    def _is_code_safe(self, code: str) -> bool:
        return True

    def _is_sql_safe(self, sql: str) -> bool:
        return True
