"""
Python code execution I/O layer implementation
"""

import tempfile
import subprocess
import os
from .base import IOLayer

class PythonCodeIOLayer(IOLayer):
    """Python code execution I/O layer"""
    def __init__(self, config: dict):
        super().__init__(config)
        self.sandbox_dir = tempfile.mkdtemp(prefix='walbert_sandbox_')

    def execute_code(self, code: str, args: list = None) -> str:
        """Execute Python code in sandboxed environment"""
        args = args or []
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', dir=self.sandbox_dir) as f:
            f.write(code)
            f.flush()

            result = subprocess.run(
                ['python3', f.name] + args,
                capture_output=True,
                text=True,
                cwd=self.sandbox_dir
            )

            return result.stdout

    def write(self, text: str) -> None:
        """Write output (not used for code execution layer)"""
        print(text)
