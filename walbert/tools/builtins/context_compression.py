"""Context compression tool for long conversations.

Adopted from AI-Builder engine best practices.
Provides a tool that summarizes conversation history to fit within
the model's context window while preserving key facts and decisions.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("walbert.tools.builtins.context_compression")


def compress_context(max_tokens: int = 4096, **kwargs) -> str:
    """Compress conversation history to fit within max_tokens.

    This is the handler function for the compress_context tool.
    It receives max_tokens as a parameter and returns a JSON string.
    """
    try:
        # Get messages from kwargs (passed by the tool executor)
        messages_str = kwargs.get("messages_json", "[]")
        messages = json.loads(messages_str) if isinstance(messages_str, str) else messages_str

        def _estimate_tokens(text: str) -> int:
            return max(1, len(text) // 4)

        if len(messages) <= 4:
            result = {
                "compressed": messages,
                "summary": "",
                "original_count": len(messages),
                "compressed_count": len(messages),
                "fits": True,
            }
        else:
            # Keep system prompt (index 0) and last 3 messages
            system_msg = messages[0] if messages else {}
            keep_messages = messages[-3:] if len(messages) > 3 else messages[1:]
            older_messages = messages[1 : len(messages) - 3] if len(messages) > 4 else []

            # Build a summary of older messages
            summary_parts = []
            for msg in older_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:200]
                if role == "user":
                    summary_parts.append(f"User: {content}")
                elif role == "assistant":
                    summary_parts.append(f"Assistant: {content}")
                elif role == "tool_result":
                    summary_parts.append(f"Tool result: {content}")

            summary = " | ".join(summary_parts[-20:])

            # Build compressed messages
            compressed = [system_msg] + keep_messages

            # Add summary as a system message
            if summary:
                compressed.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "[CONTEXT_SUMMARY]\n"
                            f"Earlier conversation (summarized):\n{summary}\n"
                            "[END_CONTEXT_SUMMARY]"
                        ),
                    },
                )

            # Verify we fit
            total_tokens = sum(_estimate_tokens(m.get("content", "")) for m in compressed)

            result = {
                "compressed": compressed,
                "summary": summary,
                "original_count": len(messages),
                "compressed_count": len(compressed),
                "estimated_tokens": total_tokens,
                "max_tokens": max_tokens,
                "fits": total_tokens <= max_tokens,
            }

        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Context compression failed: {e}")
        return json.dumps({"error": str(e), "success": False})
