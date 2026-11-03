"""Base tool class and ToolResult.

Adopted from AI-Builder engine best practices.
Provides a consistent interface for all tools.
"""

import json
from typing import Any, Dict, List, Optional


class ToolResult:
    """Wrapper for tool execution results.

    Provides a consistent return type for all tools with:
    - success: whether the tool executed successfully
    - content: the main result content (string)
    - error: error message if failed
    - file_paths: list of file paths the tool operated on
    - summary: brief summary for the LLM context
    """
    def __init__(self, success: bool, content: str, error: str = "",
                 file_paths: Optional[List[str]] = None, summary: str = ""):
        self.success = success
        self.content = content
        self.error = error
        self.file_paths = file_paths if file_paths is not None else []
        self.summary = summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "file_paths": self.file_paths,
            "summary": self.summary,
        }

    def __repr__(self):
        status = "OK" if self.success else f"ERROR: {self.error}"
        return f"ToolResult({status}, {len(self.content)} chars)"


class BaseTool:
    """Base class for all tools.

    Subclasses should define:
    - name: unique tool name (string)
    - description: tool description for the LLM prompt
    - parameters: parameter schema dict

    And implement:
    - execute(params): returns a ToolResult
    """
    name: str = ""
    description: str = ""
    parameters: Dict[str, str] = {}

    def __init__(self, root_dir: str = ""):
        self.root_dir = root_dir

    def execute(self, params: Dict[str, str]) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            params: Dictionary of parameter name -> value.

        Returns:
            ToolResult with success status, content, and optional error.
        """
        raise NotImplementedError

    def get_definition(self) -> Dict[str, Any]:
        """Return the tool definition for the LLM prompt.

        Returns:
            Dict with name, description, and parameters.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
