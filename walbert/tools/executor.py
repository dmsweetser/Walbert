"""
Tool Executor - Dispatches tool calls to their handlers.
Handles both built-in and custom (user-defined) tools.
"""

import importlib
import logging
import json
import os
import sys
import tempfile
import subprocess
from typing import Dict, Any, Optional, List

logger = logging.getLogger("walbert.tools.executor")


class ToolExecutor:
    """Executes tools by name with given parameters."""

    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_name: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Execute a tool by name with parameters.
        
        Returns:
            {"success": bool, "result": str, "error": str (optional)}
        """
        tool_def = self.registry.get_tool(tool_name)
        if not tool_def:
            return {"success": False, "result": "", "error": f"Unknown tool: {tool_name}"}

        handler_path = tool_def.get("handler", "")
        if not handler_path:
            return {"success": False, "result": "", "error": f"No handler defined for tool: {tool_name}"}

        try:
            result = self._invoke_handler(handler_path, params)
            return {"success": True, "result": result, "error": ""}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return {"success": False, "result": "", "error": f"Execution error: {str(e)}"}

    def _invoke_handler(self, handler_path: str, params: Dict[str, str]) -> str:
        """Import and invoke a handler function by dotted path."""
        module_path, func_name = handler_path.rsplit('.', 1)
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Cannot load handler '{handler_path}': {e}")

        return func(**params)
