"""
Python execution tool - run Python code in a subprocess.
"""

import os
import sys
import subprocess
import tempfile
import logging

logger = logging.getLogger("walbert.tools.builtins.python")


def execute_python(code: str = "", timeout: int = 60, **kwargs) -> str:
    """Execute Python code in a subprocess.
    
    Args:
        code: Python source code to execute.
        timeout: Maximum execution time in seconds (default 60).
    """
    if not code or not code.strip():
        return "Error: No Python code provided."
    
    script_path = None
    try:
        timeout = int(timeout) if isinstance(timeout, str) else timeout
        
        # Write code to a temp file and execute it
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as tmp:
            tmp.write(code)
            script_path = tmp.name
        
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if script_path:
            try:
                os.unlink(script_path)
            except Exception:
                pass
        
        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        output_parts.append(f"Return code: {result.returncode}")
        
        return "\n".join(output_parts)
    
    except subprocess.TimeoutExpired:
        if script_path:
            try:
                os.unlink(script_path)
            except Exception:
                pass
        return f"Python execution timed out after {timeout} seconds"
    except Exception as e:
        if script_path:
            try:
                os.unlink(script_path)
            except Exception:
                pass
        return f"Python execution error: {e}"
