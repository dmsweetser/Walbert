"""
Llama Server Model Manager - uses llama-server as a persistent background process.

llama-server keeps the KV cache in memory, so subsequent calls are much faster
than spawning a new llama-completion process each time.

Uses the OpenAI-compatible API (/v1/chat/completions) for calling the model.
"""

import os
import json
import logging
import subprocess
import time
import urllib.request
import urllib.error
import ssl
import threading
from typing import Optional

logger = logging.getLogger('walbert.models.llama_server')


class LlamaServerManager:
    """Manages a llama-server background process with HTTP API access."""

    def __init__(self, config):
        self.config = config
        self.model_config = config.model_configs.get('model', {})
        self.model_path = self.model_config.get('model_path', '')
        self.mmproj_path = config.mmproj_path or ''
        self.port = config.server_port
        self.context_size = self.model_config.get('context_size', 32768)
        self.output_tokens = self.model_config.get('output_tokens', 16384)
        self.temperature = self.model_config.get('temperature', 0.7)
        self.top_p = self.model_config.get('top_p', 0.8)
        self.top_k = self.model_config.get('top_k', 20)
        self.min_p = self.model_config.get('min_p', 0.0)
        self.server_proc = None
        self._lock = threading.Lock()
        self._started = False

    def start(self):
        """Start llama-server as a background process."""
        if self._started and self.server_proc and self.server_proc.poll() is None:
            logger.info("llama-server already running")
            return True

        if not self.model_path or not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        llama_server_path = self._find_llama_server()
        if not llama_server_path:
            raise FileNotFoundError("llama-server binary not found. Install llama.cpp.")

        cmd = [
            llama_server_path,
            "-m", self.model_path,
            "-c", str(self.context_size),
            "-ngl", "999",  # GPU layers
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--log-disable",
        ]

        # Add mmproj for multimodal models
        if self.mmproj_path and os.path.isfile(self.mmproj_path):
            cmd.extend(["--mmproj", self.mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")

        self.server_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent
        )

        # Wait for server to be ready
        if not self._wait_for_ready(self.config.server_startup_timeout):
            self.shutdown()
            raise RuntimeError(f"llama-server failed to start within {self.config.server_startup_timeout}s")

        self._started = True
        logger.info(f"llama-server started on port {self.port} (PID: {self.server_proc.pid})")
        return True

    def _find_llama_server(self) -> Optional[str]:
        """Find the llama-server binary."""
        # Check common locations
        candidates = [
            self.config.llama_binary_path.replace("llama-completion", "llama-server"),
            "llama-server",
            "/usr/local/bin/llama-server",
            "/opt/homebrew/bin/llama-server",
            os.path.join(os.path.dirname(self.config.llama_binary_path), "llama-server"),
            os.path.join(os.path.dirname(self.config.llama_binary_path), "bin", "llama-server"),
        ]

        for path in candidates:
            if path and os.path.isfile(path):
                return path

        # Try PATH
        import shutil
        found = shutil.which("llama-server")
        if found:
            return found

        return None

    def _wait_for_ready(self, timeout: int) -> bool:
        """Wait for llama-server to be ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def execute_model(self, prompt: str, callback=None, interrupt_event=None) -> str:
        """Call llama-server via HTTP API with streaming support."""
        if not self._started:
            self.start()

        model_config = self.model_config
        payload = {
            "model": "default",
            "prompt": prompt,
            "n_predict": model_config.get('output_tokens', 16384),
            "temperature": model_config.get('temperature', 0.7),
            "top_p": model_config.get('top_p', 0.8),
            "top_k": model_config.get('top_k', 20),
            "min_p": model_config.get('min_p', 0.0),
            "stream": True,
        }

        url = f"http://127.0.0.1:{self.port}/completion"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode('utf-8')

        response_content = ""
        first_token = True

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')

            # Handle SSL if needed
            context = None
            if url.startswith('https://'):
                context = ssl._create_unverified_context()

            with urllib.request.urlopen(req, context=context, timeout=300) as response:
                for line in response:
                    if interrupt_event and interrupt_event.is_set():
                        logger.info("Model execution interrupted")
                        break

                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    # llama-server streaming format: {"content":"text","stop":false}
                    try:
                        chunk = json.loads(line)
                        content = chunk.get('content', '')
                        if content:
                            response_content += content
                            if callback:
                                if first_token:
                                    callback(f"\n\n[Walbert Output]\n")
                                    first_token = False
                                callback(content)
                    except json.JSONDecodeError:
                        # Plain text response
                        response_content += line
                        if callback:
                            if first_token:
                                callback(f"\n\n[Walbert Output]\n")
                                first_token = False
                            callback(line)

        except Exception as e:
            logger.error(f"llama-server call failed: {e}")
            response_content = f"Error: llama-server call failed: {e}"

        if callback:
            callback("\n\n>>>>> ")

        return response_content

    def shutdown(self):
        """Stop the llama-server background process."""
        if self.server_proc and self.server_proc.poll() is None:
            logger.info("Stopping llama-server...")
            try:
                # Try graceful shutdown via API first
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{self.port}/quit",
                        method='POST'
                    )
                    urllib.request.urlopen(req, timeout=5)
                except Exception:
                    pass

                self.server_proc.terminate()
                self.server_proc.wait(timeout=10)
            except Exception as e:
                logger.warning(f"Error stopping llama-server: {e}")
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
        self._started = False
        self.server_proc = None
        logger.info("llama-server stopped")
