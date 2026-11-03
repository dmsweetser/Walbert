"""
Python execution tool - run Python code in a subprocess.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Proper error handling and logging
"""

import os
import sys
import subprocess
import tempfile
import logging
from typing import Dict, Any

from walbert.tools.base import BaseTool, ToolResult

logger = logging.getLogger("walbert.tools.builtins.python")


class ExecutePythonTool(BaseTool):
    name = "python_execute"
    description = "Execute Python code in a subprocess."
    parameters = {"code": "string", "timeout": "string?"}

    def execute(self, params: dict) -> ToolResult:
        code = params["code"]
        timeout = int(params.get("timeout", "60")) if params.get("timeout") else 60

        if not code or not code.strip():
            return ToolResult(False, "", error="No Python code provided.")

        script_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
                tmp.write(code)
                script_path = tmp.name

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output_parts = []
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            output_parts.append(f"Return code: {result.returncode}")

            return ToolResult(
                True, "\n".join(output_parts),
                summary=f"Python exited with code {result.returncode}"
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", error=f"Python execution timed out after {timeout} seconds")
        except Exception as e:
            return ToolResult(False, "", error=f"Python execution error: {e}")
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except Exception:
                    pass


# ===================================================================
# Backward-compatible function wrapper
# ===================================================================

def execute_python(code: str = "", timeout: str = "60", **kwargs) -> str:
    """Legacy wrapper for ExecutePythonTool."""
    tool = ExecutePythonTool(kwargs.get("root_dir", ""))
    result = tool.execute({"code": code, "timeout": timeout})
    return result.content if result.success else f"Error: {result.error}"
