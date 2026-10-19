"""
Tool Parser - Parses the custom tool format:
[TOOL:tool_name]
param1:value1
param2:
multi-line value
[TOOL_END]
"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("walbert.tools.parser")


class ToolParser:
    """Parses [TOOL:name]...[TOOL_END] blocks from LLM output."""

    TOOL_START_RE = re.compile(r'\[TOOL:([a-zA-Z0-9_]+)\]', re.IGNORECASE)
    TOOL_END_RE = re.compile(r'\[TOOL_END\]', re.IGNORECASE)

    @classmethod
    def parse(cls, text: str) -> List[Dict[str, Any]]:
        """Parse all tool blocks from text. Returns list of {name, params} dicts."""
        tools = []
        pos = 0

        while pos < len(text):
            start_match = cls.TOOL_START_RE.search(text, pos)
            if not start_match:
                break

            # Extract any text before the tool block (ignored)
            tool_name = start_match.group(1)
            content_start = start_match.end()

            # Find the matching [TOOL_END]
            end_match = cls.TOOL_END_RE.search(text, content_start)
            if not end_match:
                # Malformed: no closing tag, take rest of text
                content = text[content_start:].strip()
                end_pos = len(text)
                logger.warning(f"Tool '{tool_name}' missing [TOOL_END] tag, using rest of text")
            else:
                content = text[content_start:end_match.start()].strip()
                end_pos = end_match.end()

            # Parse key:value pairs from content
            params = cls._parse_params(content)
            tools.append({"name": tool_name, "params": params})

            pos = end_pos

        return tools

    @classmethod
    def _parse_params(cls, content: str) -> Dict[str, str]:
        """Parse key:value pairs from tool content.
        
        Supports:
          key:value           (single line)
          key:                (multi-line until next key: or end)
          key:                (empty value)
        """
        params = {}
        current_key = None
        current_value_lines = []
        lines = content.split('\n')

        for line in lines:
            # Check if this line starts a new key:value pair
            # A new key is a line that doesn't start with whitespace and contains a colon
            # But NOT lines that are continuations (start with space/tab or are blank)
            stripped = line.rstrip()
            if not stripped:
                # Blank line - could be separator in multi-line value
                if current_key is not None:
                    current_value_lines.append('')
                continue

            # Check if this is a new key:value pair
            # New key: not indented, contains ':', and the part before ':' is a valid identifier
            colon_idx = stripped.find(':')
            if colon_idx > 0 and not stripped[0].isspace() and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', stripped[:colon_idx]):
                # Save previous key's value
                if current_key is not None:
                    params[current_key] = '\n'.join(current_value_lines).rstrip()

                # Start new key
                current_key = stripped[:colon_idx].strip()
                value_part = stripped[colon_idx + 1:].strip()
                current_value_lines = [value_part] if value_part else []
            else:
                # Continuation of current multi-line value
                if current_key is not None:
                    current_value_lines.append(line)
                else:
                    # Orphaned content - skip
                    logger.debug(f"Skipping orphaned content: {stripped[:80]}")

        # Save last key
        if current_key is not None:
            params[current_key] = '\n'.join(current_value_lines).rstrip()

        return params
