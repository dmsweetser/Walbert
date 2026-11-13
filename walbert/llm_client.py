"""LLM Client - OpenAI-compatible endpoint with retry, jitter, and context trimming.

Adopted from AI-Builder engine best practices.
Provides robust LLM calls with exponential backoff, jitter, audit logging,
and token-aware context trimming to stay within the model's context window.
"""

import json
import os
import re
import time
import random
import urllib.request
import urllib.error
import ssl
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("walbert.llm_client")


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code."""
    return max(1, len(text) // 4)


def trim_messages_to_context(
    messages: List[Dict[str, str]],
    system_prompt: str,
    max_tokens: int,
) -> List[Dict[str, str]]:
    """Trim conversation history so total tokens stay within max_tokens.

    Keeps system prompt + last N messages.  max_tokens==0 means unlimited.
    Only trims when the total actually exceeds the budget.
    """
    if max_tokens <= 0:
        return messages

    system_tokens = estimate_tokens(system_prompt)

    trimmed = list(messages)
    while len(trimmed) > 1:  # keep at least the system prompt
        total = system_tokens + sum(
            estimate_tokens(m.get("content", "")) for m in trimmed[1:]
        )
        if total <= max_tokens:
            break
        # Remove the oldest non-system message (index 1)
        trimmed.pop(1)

    return trimmed


def _audit_filename(audit_dir: str, step: int) -> Tuple[str, str]:
    """Return (request_file, response_file) paths for a given step."""
    tick = f"{time.time():016.6f}".replace(".", "")[:16]
    req = os.path.join(audit_dir, f"{tick}_step{step}_request.json")
    resp = os.path.join(audit_dir, f"{tick}_step{step}_response.json")
    return req, resp


def _write_audit_file(path: str, data: Dict[str, Any]) -> None:
    """Atomically write an audit file (tmp + rename + fsync)."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"Failed to write audit file {path}: {e}")


class LLMClient:
    """Interface for calling the LLM (OpenAI-compatible endpoint).

    Features (from AI-Builder):
    - Exponential backoff with jitter on failure
    - Token-aware context trimming
    - Per-step audit logging (request + response)
    - Hard timeout per call
    - Streaming support
    """

    MAX_RETRIES = 3
    BASE_DELAY = 2.0  # seconds
    MAX_CALL_TIME = 7200  # seconds — hard timeout per LLM call

    def __init__(
        self,
        max_context_tokens: int = 0,
        max_output_tokens: int = 0,
        max_tool_result_length: int = 10000,
        audit_dir: Optional[str] = None,
    ):
        self._max_context_tokens = max_context_tokens
        self._max_output_tokens = max_output_tokens
        self._max_tool_result_length = max_tool_result_length
        self._audit_dir = audit_dir
        if self._audit_dir:
            os.makedirs(self._audit_dir, exist_ok=True)

    def call(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        step: int = 0,
    ) -> Dict[str, Any]:
        """Call the LLM with retry logic and context trimming.

        Returns a dict with:
          - 'content': the LLM response text
          - 'raw_request': the full request JSON (truncated to 3000 chars)
          - 'raw_response': the full response text (truncated to 2000 chars)
        """
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._call_endpoint(messages, system_prompt, step)
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (2 ** (attempt - 1))
                    jitter = delay * (0.5 + 0.5 * random.random())
                    logger.warning(
                        f"LLM call attempt {attempt}/{self.MAX_RETRIES} failed: {e}. "
                        f"Retrying in {jitter:.1f}s..."
                    )
                    time.sleep(jitter)

        raise RuntimeError(
            f"LLM call failed after {self.MAX_RETRIES} attempts: {last_err}"
        )

    def _call_endpoint(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        step: int,
    ) -> Dict[str, Any]:
        """Call the configured endpoint (Ollama, LM Studio, vLLM, etc.)."""
        from walbert.config import Config

        # Read config values at call time (not import time)
        try:
            import walbert.config as _cfg
            endpoint_url = getattr(_cfg, "_custom_endpoint_url", None) or os.environ.get(
                "WALBERT_ENDPOINT_URL", ""
            )
            api_key = getattr(_cfg, "_custom_api_key", None) or os.environ.get(
                "WALBERT_API_KEY", ""
            )
            model_name = getattr(_cfg, "_custom_model_name", None) or os.environ.get(
                "WALBERT_MODEL_NAME", ""
            )
            timeout = int(
                getattr(_cfg, "_timeout", None)
                or os.environ.get("WALBERT_TIMEOUT", "300")
            )
            verify_ssl = getattr(_cfg, "_verify_ssl", None)
            if verify_ssl is None:
                verify_ssl = os.environ.get("WALBERT_VERIFY_SSL", "false").lower() not in (
                    "false", "0", ""
                )
        except Exception:
            endpoint_url = os.environ.get("WALBERT_ENDPOINT_URL", "")
            api_key = os.environ.get("WALBERT_API_KEY", "")
            model_name = os.environ.get("WALBERT_MODEL_NAME", "")
            timeout = int(os.environ.get("WALBERT_TIMEOUT", "300"))
            verify_ssl = os.environ.get("WALBERT_VERIFY_SSL", "false").lower() not in (
                "false", "0", ""
            )

        if not all([endpoint_url, model_name]):
            raise RuntimeError(
                "Missing LLM config: WALBERT_ENDPOINT_URL and WALBERT_MODEL_NAME "
                "environment variables (or config) are required"
            )

        # Trim messages to context budget
        if self._max_context_tokens > 0 and system_prompt:
            messages = trim_messages_to_context(
                messages, system_prompt, self._max_context_tokens
            )

        # Build OpenAI-format messages
        openai_messages = [
            {"role": msg["role"], "content": msg.get("content", "")}
            for msg in messages
        ]

        # --- Audit: log the full request ---
        req_file, resp_file = _audit_filename(self._audit_dir or "", step)
        if req_file:
            audit_payload = {
                "step": step,
                "timestamp": time.time(),
                "model": model_name,
                "endpoint": endpoint_url,
                "message_count": len(openai_messages),
                "messages": openai_messages,
            }
            _write_audit_file(req_file, audit_payload)

        # Build payload
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": openai_messages,
            "stream": True,
        }
        if self._max_output_tokens > 0:
            payload["max_tokens"] = self._max_output_tokens

        # Build headers
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        data = json.dumps(payload).encode("utf-8")

        # SSL context
        if verify_ssl is False:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx = None

        # Send request
        req = urllib.request.Request(
            endpoint_url,
            data=data,
            headers=headers,
            method="POST",
        )

        response_parts = []
        total_time = 0
        start_time = time.time()

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                for line in resp:
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    line = line.strip()
                    if not line:
                        continue
                    # Parse SSE data line
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                response_parts.append(delta)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
                    total_time = time.time() - start_time
                    # Hard timeout
                    if total_time > self.MAX_CALL_TIME:
                        raise TimeoutError(
                            f"LLM call exceeded {self.MAX_CALL_TIME}s"
                        )
        except Exception as e:
            raise RuntimeError(f"LLM HTTP request failed: {e}") from e

        content = "".join(response_parts)

        # --- Audit: log the response ---
        if resp_file:
            _write_audit_file(
                resp_file,
                {
                    "step": step,
                    "timestamp": time.time(),
                    "model": model_name,
                    "content_length": len(content),
                    "raw_response": content[:2000],
                    "total_time_s": round(total_time, 2),
                },
            )

        return {
            "content": content,
            "raw_request": json.dumps(payload)[:3000],
            "raw_response": content[:2000],
        }

    def truncate_result(self, content: str, tool_name: str = "") -> Tuple[str, bool]:
        """Truncate a tool result if it exceeds max_tool_result_length.

        Returns (truncated_content, was_truncated) tuple.
        """
        if self._max_tool_result_length <= 0 or len(content) <= self._max_tool_result_length:
            return content, False

        tail = content[-200:] if len(content) > self._max_tool_result_length + 200 else ""
        truncated = (
            content[: self._max_tool_result_length]
            + f'\n\n... [TRUNCATED - output was too long, '
            f"showing first {self._max_tool_result_length} of {len(content)} characters]"
        )
        return truncated, True
