"""Status file helpers for real-time agent monitoring.

Adopted from AI-Builder engine best practices.
Provides crash-safe status file writes and live instruction / user input
polling via status.json.
"""

import json
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("walbert.status_file")


def _write_status_file(output_dir: str, status_data: Dict[str, Any]) -> None:
    """Atomically write status.json in the output directory.

    Uses a temp file + os.replace + fsync so readers never see a
    half-written file.
    """
    status_file = os.path.join(output_dir, "status.json")
    tmp_file = status_file + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, status_file)
    except Exception as e:
        logger.warning(f"Failed to write status file {status_file}: {e}")


def _read_status_file(output_dir: str) -> Dict[str, Any]:
    """Read status.json from disk. Returns empty dict on failure."""
    status_file = os.path.join(output_dir, "status.json")
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def init_status_file(output_dir: str, job_id: str = "") -> None:
    """Create an initial status.json for a new run."""
    _write_status_file(
        output_dir,
        {
            "status": "running",
            "step": 0,
            "timestamp": __import__("time").time(),
            "job_id": job_id,
        },
    )


def update_status(
    output_dir: str,
    status: str = "running",
    step: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Update the status file with new values."""
    current = _read_status_file(output_dir)
    if status:
        current["status"] = status
    if step is not None:
        current["step"] = step
    current["timestamp"] = __import__("time").time()
    if extra:
        current.update(extra)
    _write_status_file(output_dir, current)


def set_pending_live_instruction(output_dir: str, instruction: str) -> None:
    """Set a pending live instruction that the agent will pick up.

    The instruction is consumed (removed) after the agent reads it,
    making this idempotent.
    """
    status = _read_status_file(output_dir)
    status["pending_live_instruction"] = instruction
    _write_status_file(output_dir, status)


def get_pending_live_instruction(output_dir: str) -> Optional[str]:
    """Read and consume a pending live instruction.

    Returns the instruction text, or None if no instruction is pending.
    """
    status = _read_status_file(output_dir)
    pending = status.get("pending_live_instruction")
    if pending:
        status.pop("pending_live_instruction")
        _write_status_file(output_dir, status)
        return pending
    return None


def set_pending_user_input(
    output_dir: str, question: str, timeout: int = 300
) -> None:
    """Set a pending user input request.

    The agent polls for the answer via get_pending_user_input().
    The dict stores the question and timeout for the UI.
    """
    status = _read_status_file(output_dir)
    status["pending_user_input"] = {
        "question": question,
        "timeout": timeout,
        "set_at": __import__("time").time(),
    }
    _write_status_file(output_dir, status)


def get_pending_user_input(output_dir: str) -> Optional[str]:
    """Read and consume a pending user input answer.

    Returns the answer string, or None if no answer is pending.
    The UI should write the answer to status.json as:
        {"pending_user_input": {"question": "...", "answer": "..."}}
    """
    status = _read_status_file(output_dir)
    pending = status.get("pending_user_input")
    if not pending or not isinstance(pending, dict):
        return None
    answer = pending.get("answer")
    if answer:
        # Consume it — restore just the question for idempotency
        status["pending_user_input"] = {
            "question": pending.get("question", ""),
        }
        _write_status_file(output_dir, status)
        return answer
    return None


def write_step_file(output_dir: str, step_num: int, step_data: Dict[str, Any]) -> None:
    """Atomically write a step record to steps/NNN.json.

    Creates the steps/ subdirectory if needed. Uses a temp file + atomic
    rename so readers never see a half-written file.
    """
    steps_dir = os.path.join(output_dir, "steps")
    os.makedirs(steps_dir, exist_ok=True)
    step_file = os.path.join(steps_dir, f"{step_num:04d}.json")
    tmp_file = step_file + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(step_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, step_file)
    except Exception as e:
        logger.warning(f"Failed to write step file {step_file}: {e}")
