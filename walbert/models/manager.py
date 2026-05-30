"""
Model manager implementation
"""

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
            self.server = self.start_server(self.config.mmproj_path)
            if not self.wait_for_server():
                logger.error("Model server failed to start")
                return
            logger.info("Model server started successfully")

        self.server_thread = threading.Thread(target=start, daemon=True)
        self.server_thread.start()
        self.server_thread.join(timeout=60)

    def execute_model(self, prompt: str) -> str:
        """Execute model using existing server"""
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
            "stream": False
        }

        try:
            try:
                response = requests.post(
                    "http://localhost:8080/v1/chat/completions",
                    json=payload,
                    timeout=7200
                )
                response.raise_for_status()
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                else:
                    raise RuntimeError(f"Invalid response format: {result}")
            except Exception as e:
                logger.error(f"Error executing model: {e}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error communicating with model server: {e}")
            raise RuntimeError(f"Model server error: {e}")

    def shutdown(self):
        """Shutdown model server"""
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server.kill()

        logger.info("Model server shutdown complete")
