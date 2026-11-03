"""Security helpers for Walbert tools.

Adopted from AI-Builder engine best practices.
Provides path validation, parameter validation, and a clean exception hierarchy.
"""

import os
import re
from typing import Any, Dict, List, Optional


class SecurityError(Exception):
    """Security violation — path escapes project root."""
    pass


class ToolError(Exception):
    """Tool-specific error (bad params, operation failed)."""
    pass


class EngineError(Exception):
    """Engine-level fatal error."""
    pass


# Well-known directories where absolute paths are allowed
ALLOWED_ABSOLUTE_PREFIXES = [
    "/tmp/", "/tmp",
    "/var/tmp/", "/var/tmp",
]


def ensure_under_root(filepath: str, root_dir: str, allow_walbert_instance: bool = True) -> str:
    """Resolve and validate that a path stays within root_dir.

    Args:
        filepath: The path provided by the tool caller (LLM).
        root_dir: The allowed root directory (project root or Walbert instance dir).
        allow_walbert_instance: If True, also allow paths under the Walbert instance directory.

    Returns:
        The resolved absolute path.

    Raises:
        SecurityError: If the path escapes the allowed root.
    """
    root_dir = _normalize_path(root_dir)

    # Normalize the input path
    normalized = _normalize_path(filepath)

    # Handle Windows-style absolute paths (e.g. C:/...) — treat as relative
    if re.match(r'^[A-Z]:/', normalized, re.IGNORECASE):
        rel_path = normalized[2:]
        if rel_path.startswith('/'):
            rel_path = rel_path[1:]
        full = _normalize_path(os.path.join(root_dir, rel_path))
        if full == root_dir or full.startswith(root_dir + '/'):
            return full
        raise SecurityError(f"Path escapes project root: {filepath} -> {full}")

    if os.path.isabs(filepath):
        full = normalized
        # Allow absolute paths that equal the root_dir itself
        if full == root_dir:
            return full
        # Allow absolute paths within root_dir (not just root_dir/instance)
        if full.startswith(root_dir + '/') or full == root_dir:
            return full
        # Allow absolute paths under the Walbert instance directory
        if allow_walbert_instance:
            walbert_instance = _normalize_path(os.path.join(root_dir, "instance"))
            if full == walbert_instance or full.startswith(walbert_instance + '/'):
                return full
        # Allow absolute paths in well-known writable directories
        for prefix in ALLOWED_ABSOLUTE_PREFIXES:
            if full == prefix or full.startswith(prefix):
                return full
        raise SecurityError(f"Absolute path escapes project root: {filepath} -> {full}")
    else:
        full = _normalize_path(os.path.join(root_dir, filepath))

    if full == root_dir or full.startswith(root_dir + '/'):
        return full
    raise SecurityError(f"Path escapes project root: {filepath} -> {full}")


def validate_tool_params(params: Dict[str, Any], schema: Dict[str, str]) -> Dict[str, Any]:
    """Validate that all required params are present and are strings.

    Parameters with a 'string?' type are optional.

    Args:
        params: The raw parameters from the tool call.
        schema: Tool parameter schema (keys are param names, values are type strings).

    Returns:
        Validated parameters dict.

    Raises:
        ToolError: If a required parameter is missing or has wrong type.
    """
    result = {}
    for key, expected_type in schema.items():
        optional = expected_type.endswith("?")
        if optional:
            expected_type = expected_type[:-1]
        if key not in params:
            if optional:
                continue
            raise ToolError(f"Missing required parameter: {key}")
        val = params[key]
        if expected_type == "string" and not isinstance(val, str):
            raise ToolError(f"Parameter '{key}' must be a string, got {type(val).__name__}")
        result[key] = val
    return result


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison.

    Handles cross-platform path formats including WSL/Cygwin-style paths.
    """
    if not path:
        return path

    p = path.strip()
    p = p.replace('\\', '/')

    # Handle WSL/Cygwin-style paths: /c/local -> C:/local
    m = re.match(r'^/([a-zA-Z]):?(/.*)$', p)
    if m:
        p = m.group(1).upper() + ':' + m.group(2)

    p = os.path.normpath(p)
    p = p.replace('\\', '/')

    return p


def truncate_tool_result(content: str, max_length: int, tool_name: str = "") -> tuple:
    """Truncate a tool result if it exceeds max_length characters.

    Args:
        content: The tool result content.
        max_length: Maximum allowed length (0 = no truncation).
        tool_name: Name of the tool (for hint messages).

    Returns:
        (truncated_content, was_truncated) tuple.
    """
    if max_length <= 0 or len(content) <= max_length:
        return content, False

    tail = content[-200:] if len(content) > max_length + 200 else ""
    truncated = content[:max_length] + f"\n\n... [TRUNCATED - output was too long, " \
               f"showing first {max_length} of {len(content)} characters]"

    return truncated, True
