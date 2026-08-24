import os
import sys
import tempfile
import subprocess
from typing import Dict, Optional

class BlockExecutor:
    def __init__(self, config, db_manager):
        self.config = config
        self.db = db_manager

    def execute(self, block: Dict[str, str]) -> Optional[Dict[str, str]]:
        block_type = block["type"]
        content = block["content"]

        if block_type == "sql_execute":
            return self._execute_sql(content)

        elif block_type == "python_execute":
            return self._execute_python(content)

        elif block_type == "bash_execute":
            return self._execute_bash(content)

        elif block_type == "console_response_blocking":
            return {"type": "console_response_blocking", "content": f"Walbert:\n{content}\n"}

        elif block_type == "console_response_nonblocking":
            return {"type": "console_response_nonblocking", "content": f"Walbert:\n{content}\n"}

        return None

    # ---------------- SQL ----------------

    def _execute_sql(self, sql: str) -> Dict[str, str]:
        try:
            result = self.db.execute_sql(sql)
            return {"type": "sql_result", "content": f"{result}\n"}
        except Exception as e:
            return {"type": "sql_result", "content": f"SQL execution error: {str(e)}"}

    # ---------------- PYTHON ----------------

    def _execute_python(self, code: str) -> Dict[str, str]:
        if not self.config.python_execution_enabled:
            return {"type": "python_result", "content": "Python execution is disabled."}

        try:
            # Write code exactly as provided
            with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
                tmp.write(code.encode("utf-8"))
                script_path = tmp.name

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=self.config.python_execution_timeout
            )

            output = []
            if result.stdout:
                output.append("Python stdout:\n" + result.stdout)
            if result.stderr:
                output.append("Python stderr:\n" + result.stderr)
            output.append(f"Python return code: {result.returncode}")

            return {"type": "python_result", "content": "\n".join(output)}

        except subprocess.TimeoutExpired:
            return {"type": "python_result",
                    "content": f"Python execution timed out after {self.config.python_execution_timeout} seconds"}

        except Exception as e:
            return {"type": "python_result", "content": f"Python execution error: {str(e)}"}

    # ---------------- BASH ----------------

    def _execute_bash(self, code: str) -> Dict[str, str]:
        if not self.config.bash_execution_enabled:
            return {"type": "bash_result", "content": "Bash execution is disabled."}

        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                timeout=self.config.bash_execution_timeout
            )

            output = []
            if result.stdout:
                output.append("Bash stdout:\n" + result.stdout)
            if result.stderr:
                output.append("Bash stderr:\n" + result.stderr)
            output.append(f"Bash return code: {result.returncode}")

            return {"type": "bash_result", "content": "\n".join(output)}

        except subprocess.TimeoutExpired:
            return {"type": "bash_result",
                    "content": f"Bash execution timed out after {self.config.bash_execution_timeout} seconds"}

        except Exception as e:
            return {"type": "bash_result", "content": f"Bash execution error: {str(e)}"}
