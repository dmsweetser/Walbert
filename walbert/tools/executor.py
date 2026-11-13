"""Tool Executor - Dispatches tool calls to their handlers.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Supports both class-based tools (BaseTool subclasses) and legacy handler-path tools
- Proper error handling, logging, and result length limits
- Max result length truncation to prevent context bloat
"""

import importlib
import logging
import json
import os
import sys
import tempfile
from typing import Dict, Any, Optional, List, Tuple

from walbert.tools.base import BaseTool, ToolResult
from walbert.tools.security import ToolError, SecurityError, EngineError

logger = logging.getLogger("walbert.tools.executor")


def truncate_result(content: str, max_length: int) -> Tuple[str, bool]:
    """Truncate a tool result if it exceeds max_length characters.

    Returns (truncated_content, was_truncated) tuple.
    """
    if max_length <= 0 or len(content) <= max_length:
        return content, False

    tail = content[-200:] if len(content) > max_length + 200 else ""
    truncated = (
        content[:max_length]
        + f'\n\n... [TRUNCATED - output was too long, '
        f"showing first {max_length} of {len(content)} characters]"
    )
    return truncated, True


class ToolExecutor:
    """Executes tools by name with given parameters.

    Supports:
    - Class-based tools (BaseTool subclasses with execute(params) -> ToolResult)
    - Legacy handler-path tools (function references like "module.func")

    Features (from AI-Builder):
    - Max result length truncation to prevent context bloat
    - Consistent error handling across all tool types
    """

    DEFAULT_MAX_RESULT_LENGTH = 10000

    def __init__(self, registry, max_result_length: int = DEFAULT_MAX_RESULT_LENGTH):
        self.registry = registry
        self.max_result_length = max_result_length

    def execute(self, tool_name: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Execute a tool by name with parameters.

        Returns:
            Dict with 'success', 'result', 'error', 'file_paths', 'summary' keys.
        """
        tool = self.registry.get_tool(tool_name)
        if not tool:
            available = list(self.registry.list_tools_raw().keys())
            logger.warning(f"Unknown tool: {tool_name}. Available: {available}")
            return {
                "success": False,
                "result": "",
                "error": f"Unknown tool: {tool_name}. Available: {', '.join(available[:10])}",
                "file_paths": [],
                "summary": "",
            }

        try:
            result = self._invoke_tool(tool, tool_name, params)
            if not isinstance(result, ToolResult):
                return {
                    "success": False,
                    "result": "",
                    "error": f"Tool returned non-ToolResult: {type(result)}",
                    "file_paths": [],
                    "summary": "",
                }

            # Truncate result content if needed
            truncated, was_truncated = truncate_result(
                result.content, self.max_result_length
            )
            if was_truncated:
                result.content = truncated
                result.summary += " (result truncated)"

            return result.to_dict()
        except (SecurityError, ToolError) as e:
            logger.warning(f"Tool {tool_name} error: {e}")
            return ToolResult(False, "", error=str(e)).to_dict()
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return ToolResult(False, "", error=f"Execution error: {str(e)}").to_dict()

    def _invoke_tool(
        self, tool: Any, tool_name: str, params: Dict[str, str]
    ) -> ToolResult:
        """Invoke a tool, handling both class-based and legacy handler-path formats."""
        # Class-based tool (BaseTool subclass)
        if isinstance(tool, BaseTool):
            return tool.execute(params)

        # Legacy handler-path tool
        if isinstance(tool, dict) and "handler" in tool:
            handler_path = tool["handler"]
            return self._invoke_handler(handler_path, params)

        # Tool registered without handler (custom class)
        if hasattr(tool, "execute") and callable(getattr(tool, "execute")):
            return tool.execute(params)

        return ToolResult(
            False, "", error=f"No handler defined for tool: {tool_name}"
        )

    def _invoke_handler(
        self, handler_path: str, params: Dict[str, str]
    ) -> ToolResult:
        """Import and invoke a handler function by dotted path.

        The handler function receives **kwargs and returns a string result.
        Wraps the string result in a ToolResult.
        """
        module_path, func_name = handler_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Cannot load handler '{handler_path}': {e}")

        try:
            result_str = func(**params)
            return ToolResult(
                success=True,
                content=str(result_str),
                summary=f"Executed {func_name}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Handler error in {func_name}: {str(e)}",
            )
