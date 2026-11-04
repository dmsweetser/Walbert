"""Mock HTTP LLM server for end-to-end testing.

Simulates a llama-server compatible HTTP API endpoint so tests can
exercise the full agent loop without requiring an actual model binary.
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional


class MockLLMHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns mock LLM responses."""

    # Class-level callback: set this to customize responses
    response_callback: Optional[Callable[[str, dict], dict]] = None
    # Counter for tracking call order
    call_count = 0
    call_history = []

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass

    def do_POST(self):
        """Handle POST requests to /v1/chat/completions."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        # Track the call
        MockLLMHandler.call_count += 1
        MockLLMHandler.call_history.append({
            "request": request_data,
            "timestamp": time.time()
        })

        # Generate response via callback or default
        if MockLLMHandler.response_callback:
            response = MockLLMHandler.response_callback(
                request_data.get("model", ""),
                request_data
            )
        else:
            response = self._default_response(request_data)

        self._send_json(200, response)

    def do_GET(self):
        """Handle GET requests for health checks."""
        if self.path == "/health" or self.path == "/v1/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [
                    {
                        "id": "mock-llm",
                        "object": "model",
                        "owned_by": "test"
                    }
                ]
            })
        else:
            self._send_error(404, "Not found")

    def _default_response(self, request_data: dict) -> dict:
        """Default mock response - returns a simple tool call."""
        messages = request_data.get("messages", [])
        user_msg = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")

        # Default: return a tool call for shell_run
        response = {
            "id": "mock-123",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "mock-llm",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": self._default_content(user_msg)
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }
        return response

    def _default_content(self, user_msg: str) -> str:
        """Generate default tool call content."""
        return """[TOOL_START]
[TOOL_NAME]shell_run
[PARAM_COMMAND]
[PARAM_VALUE]echo "autonomous check"
[TOOL_END]

Autonomous check complete."""

    def _send_json(self, status: int, data: dict):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, status: int, message: str):
        """Send an error response."""
        self._send_json(status, {"error": message})


def start_mock_server(port: int = 19999, blocking: bool = False) -> HTTPServer:
    """Start a mock LLM HTTP server.

    Args:
        port: Port to listen on (default 19999)
        blocking: If False, run in background thread

    Returns:
        The HTTPServer instance
    """
    server = HTTPServer(("127.0.0.1", port), MockLLMHandler)
    if not blocking:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.2)  # Let server start
    else:
        server.serve_forever()
    return server


def stop_mock_server(server: HTTPServer):
    """Stop a mock LLM server."""
    server.shutdown()
    server.server_close()


def reset_mock_server():
    """Reset mock server state (call count, history, callback)."""
    MockLLMHandler.call_count = 0
    MockLLMHandler.call_history = []
    MockLLMHandler.response_callback = None
