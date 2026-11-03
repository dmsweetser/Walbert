"""
Tool Parser - Parses tool calls from LLM output.

Supports two formats (adopted from AI-Builder best practices):
1. Walbert legacy: [TOOL:tool_name] ... [TOOL_END]
2. AI-Builder: [TOOL_START] ... [TOOL_END] with [PARAM_NAME]/[PARAM_VALUE] tags

Also extracts [RATIONALE] blocks for explaining reasoning.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("walbert.tools.parser")


class ToolParser:
    """Parses tool blocks from LLM output.

    Supports both:
    - [TOOL:name]...[TOOL_END] format (legacy Walbert)
    - [TOOL_START]...[TOOL_END] format (AI-Builder style with PARAM_NAME/PARAM_VALUE)
    """

    TOOL_START_RE = re.compile(r'\[TOOL:([a-zA-Z0-9_]+)\]', re.IGNORECASE)
    TOOL_END_RE = re.compile(r'\[TOOL_END\]', re.IGNORECASE)
    TOOL_START_BLOCK_RE = re.compile(r'\[TOOL_START\]', re.IGNORECASE)
    TOOL_NAME_TAG_RE = re.compile(r'\[TOOL_NAME\]', re.IGNORECASE)
    PARAM_NAME_TAG_RE = re.compile(r'\[PARAM_NAME\]', re.IGNORECASE)
    PARAM_VALUE_TAG_RE = re.compile(r'\[PARAM_VALUE\]', re.IGNORECASE)
    RATIONALE_TAG_RE = re.compile(r'\[RATIONALE\]', re.IGNORECASE)

    @classmethod
    def parse(cls, text: str) -> List[Dict[str, Any]]:
        """Parse all tool blocks from text.

        Returns list of {name, params, rationale} dicts.
        Tries AI-Builder format first, falls back to legacy format.
        """
        # Try AI-Builder format first: [TOOL_START]...[TOOL_END]
        ai_builder_calls = cls._parse_ai_builder_format(text)
        if ai_builder_calls:
            return ai_builder_calls

        # Fallback to legacy format: [TOOL:name]...[TOOL_END]
        return cls._parse_legacy_format(text)

    @classmethod
    def _parse_ai_builder_format(cls, text: str) -> List[Dict[str, Any]]:
        """Parse [TOOL_START]...[TOOL_END] blocks with PARAM_NAME/PARAM_VALUE tags."""
        calls = []
        # Find all [TOOL_START]...[TOOL_END] blocks
        pattern = re.compile(r'\[TOOL_START\](.*?)\[TOOL_END\]', re.DOTALL)

        for match in pattern.finditer(text):
            block = match.group(1)

            # Extract tool name from [TOOL_NAME] tag
            tool_name = cls._extract_tool_name_from_block(block)
            if not tool_name:
                # Try to extract from [TOOL_START][tool_name] pattern
                alt_match = re.match(r'\s*\[([a-zA-Z0-9_]+)\]\s*', block)
                if alt_match:
                    tool_name = alt_match.group(1)
                    block = block[alt_match.end():]
                else:
                    continue

            # Extract parameters
            params = cls._parse_params_from_block(block)

            # Extract rationale
            rationale = cls._extract_rationale(block)

            calls.append({
                "name": tool_name,
                "params": params,
                "rationale": rationale,
            })

        return calls

    @classmethod
    def _extract_tool_name_from_block(cls, block: str) -> Optional[str]:
        """Extract tool name from [TOOL_NAME] tag in a block."""
        name_match = re.search(r'\[TOOL_NAME\]\s*\n?\s*([a-zA-Z0-9_]+)', block)
        if name_match:
            return name_match.group(1).strip()
        return None

    @classmethod
    def _parse_params_from_block(cls, block: str) -> Dict[str, str]:
        """Parse PARAM_XXX/VALUE pairs from a block.

        Supports any [PARAM_XXX] tag as a parameter name, followed by
        [PARAM_VALUE] with the value. Also supports [TOOL_NAME] as the
        first parameter (the tool name itself).
        """
        params = {}

        # Match any [PARAM_XXX] tag followed by [PARAM_VALUE]
        # Pattern: [PARAM_XXX] key [PARAM_VALUE] value
        param_tag_pattern = re.compile(r'\[PARAM_([A-Z_]+)\]\s*\n?\s*(.*?)(?=\[PARAM_|$)', re.DOTALL)
        value_pattern = re.compile(r'\[PARAM_VALUE\]\s*\n?\s*(.*?)(?=\[PARAM_|$)', re.DOTALL)

        # Find all param tags and their values
        param_tags = list(param_tag_pattern.finditer(block))
        param_values = list(value_pattern.finditer(block))

        # Pair them up: each PARAM_XXX is followed by a PARAM_VALUE
        for tag_match, val_match in zip(param_tags, param_values):
            # Strip "PARAM_" prefix and lowercase: PARAM_PATH -> path, PARAM_COMMAND -> command
            raw_key = tag_match.group(1)
            # Remove trailing VALUE if present (PARAM_VALUE -> value)
            if raw_key == "VALUE":
                continue  # Skip standalone PARAM_VALUE
            key = raw_key.lower()
            value = val_match.group(1).strip()
            if key and value:
                params[key] = value

        return params if params else {}

    @classmethod
    def _extract_rationale(cls, block: str) -> Optional[str]:
        """Extract [RATIONALE] block from params if present."""
        rationale_match = re.search(r'\[RATIONALE\]\s*\n(.*?)(?=\[TOOL_END\]|\[TOOL_NAME\]|\Z)', block, re.DOTALL)
        if rationale_match:
            rationale = rationale_match.group(1).strip()
            if rationale:
                return rationale
        return None

    @classmethod
    def _parse_legacy_format(cls, text: str) -> List[Dict[str, Any]]:
        """Parse [TOOL:name]...[TOOL_END] blocks (legacy Walbert format)."""
        tools = []
        pos = 0

        while pos < len(text):
            start_match = cls.TOOL_START_RE.search(text, pos)
            if not start_match:
                break

            tool_name = start_match.group(1)
            content_start = start_match.end()

            end_match = cls.TOOL_END_RE.search(text, content_start)
            if not end_match:
                content = text[content_start:].strip()
                end_pos = len(text)
                logger.warning(f"Tool '{tool_name}' missing [TOOL_END] tag, using rest of text")
            else:
                content = text[content_start:end_match.start()].strip()
                end_pos = end_match.end()

            params = cls._parse_legacy_params(content)
            tools.append({
                "name": tool_name,
                "params": params,
                "rationale": None,
            })

            pos = end_pos

        return tools

    @classmethod
    def _parse_legacy_params(cls, content: str) -> Dict[str, str]:
        """Parse key:value pairs from legacy tool content.

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
            stripped = line.rstrip()
            if not stripped:
                if current_key is not None:
                    current_value_lines.append('')
                continue

            colon_idx = stripped.find(':')
            if colon_idx > 0 and not stripped[0].isspace() and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', stripped[:colon_idx]):
                if current_key is not None:
                    params[current_key] = '\n'.join(current_value_lines).rstrip()

                current_key = stripped[:colon_idx].strip()
                value_part = stripped[colon_idx + 1:].strip()
                current_value_lines = [value_part] if value_part else []
            else:
                if current_key is not None:
                    current_value_lines.append(line)
                else:
                    logger.debug(f"Skipping orphaned content: {stripped[:80]}")

        if current_key is not None:
            params[current_key] = '\n'.join(current_value_lines).rstrip()

        return params
