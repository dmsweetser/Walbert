"""
Model manager implementation
"""

import json
import os
import subprocess
import logging
import threading
import time
import requests
from typing import Optional
from ..config import Config, ModelConfig

logger = logging.getLogger('walbert')

class ModelManager:
    """Manages model execution through llama.cpp binaries"""
    def __init__(self, config: Config):
        self.config = config
        self.server = None
        self.server_thread = None
        self.validate_binaries()
        self.start_server()

    def validate_binaries(self):
        """Validate that all required binaries exist"""
        if not os.path.isfile(self.config.llama_binary_path):
            raise FileNotFoundError(f"llama.cpp binary not found at {self.config.llama_binary_path}")

        for model_name, model_config in self.config.model_configs.items():
            if not os.path.isfile(model_config.model_path):
                raise FileNotFoundError(f"{model_name} model not found at {model_config.model_path}")

    def start_server(self, mmproj_path: Optional[str] = None) -> subprocess.Popen:
        """Start a llama.cpp server instance"""
        model_config = self.config.model_configs['model']
        cmd = [
            self.config.llama_binary_path,
            "-m", model_config.model_path,
            "--ctx-size", str(model_config.context_size),
            "--jinja",
            "--temp", str(model_config.temperature),
            "--top-p", str(model_config.top_p),
            "--top-k", str(model_config.top_k),
            "--min-p", str(model_config.min_p),
            "--port", str(self.config.server_port)
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def wait_for_server(self, timeout: int = None):
        """Wait for server to be ready"""
        if timeout is None:
            timeout = self.config.server_startup_timeout
        """Wait for server to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get("http://localhost:8080/health", timeout=2)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def start_server_thread(self):
        """Start model server in background thread"""
        def start():
            # Ensure old server is shut down before starting a new one to prevent multiple instances
            if self.server and self.server.poll() is None:
                self.shutdown()
            
            self.server = self.start_server(self.config.mmproj_path)
            if not self.wait_for_server():
                logger.error("Model server failed to start")
                return
            logger.info("Model server started successfully")

        self.server_thread = threading.Thread(target=start)
        self.server_thread.daemon = True
        self.server_thread.start()

    def execute_model(self, prompt: str, callback=None, interrupt_event=None) -> str:
        """Execute model using existing server with streaming support and interrupt capability"""
        model_config = self.config.model_configs['model']
        payload = {
            "model": "default",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": model_config.output_tokens,
            "temperature": model_config.temperature,
            "top_p": model_config.top_p,
            "top_k": model_config.top_k,
            "min_p": model_config.min_p,
            "stream": True
        }

        try:
            try:
                full_response = ""
                response = requests.post(
                    "http://localhost:8080/v1/chat/completions",
                    json=payload,
                    timeout=7200,
                    stream=True
                )
                response.raise_for_status()

                for line in response.iter_lines():
                    if interrupt_event and interrupt_event.is_set():
                        logger.info("Model execution interrupted by user")
                        return full_response

                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            line_str = line_str[6:]
                            if line_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(line_str)
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    content = chunk["choices"][0].get("delta", {}).get("content", "")
                                    if content:
                                        if interrupt_event and interrupt_event.is_set():
                                            logger.info("Model execution interrupted by user")
                                            return full_response
                                        if full_response == "":
                                            callback(f"{chr(10)}{chr(10)}[Walbert Output]{chr(10)}")
                                        full_response += content
                                        if callback:
                                            callback(content)
                            except json.JSONDecodeError:
                                continue

                return full_response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    logger.error(f"Bad request error executing model: {e}")
                    logger.info("Attempting to restart model server...")
                    self.shutdown()
                    time.sleep(2)
                    self.start_server_thread()
                    if not self.wait_for_server():
                        raise RuntimeError("Model server failed to restart after 400 error")
                    logger.info("Model server restarted successfully")
                    # Retry the request once after restart
                    return self.execute_model(prompt, callback, interrupt_event)
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.error(f"Connection error executing model: {e}")
                self.shutdown()
                time.sleep(2)
                self.start_server_thread()
                if not self.wait_for_server():
                    raise RuntimeError("Model server failed to restart after connection error")
                logger.info("Model server restarted successfully")
                # Retry the request once after restart
                return self.execute_model(prompt, callback, interrupt_event)
            except Exception as e:
                logger.error(f"Error executing model: {e}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error communicating with model server: {e}")
            raise RuntimeError(f"Model server error: {e}")

    def shutdown(self):
        """Shutdown model server"""
        if self.server_thread and self.server_thread.is_alive():
            # Immediately terminate the server process
            if self.server and self.server.poll() is None:
                self.server.terminate()
                try:
                    self.server.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.server.kill()

            # Forcefully stop the server thread
            if hasattr(self.server_thread, '_stop'):
                self.server_thread._stop()

        logger.info("Model server shutdown complete")
