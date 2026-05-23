"""
Model manager implementation
"""

import os
import subprocess
import logging
import threading
import time
import requests
from typing import Optional, Dict
from ..config import Config, ModelConfig

logger = logging.getLogger('walbert')

class ModelManager:
    """Manages model execution through llama.cpp binaries"""
    def __init__(self, config: Config):
        self.config = config
        self.ministral_server = None
        self.devstral_server = None
        self.ministral_thread = None
        self.devstral_thread = None
        self.validate_binaries()
        self.start_servers()

    def validate_binaries(self):
        """Validate that all required binaries exist"""
        if not os.path.isfile(self.config.llama_binary_path):
            raise FileNotFoundError(f"llama.cpp binary not found at {self.config.llama_binary_path}")

        for model_name, model_config in self.config.model_configs.items():
            if not os.path.isfile(model_config.model_path):
                raise FileNotFoundError(f"{model_name} model not found at {model_config.model_path}")

    def start_server(self, model_config: ModelConfig, mmproj_path: Optional[str] = None) -> subprocess.Popen:
        """Start a llama.cpp server instance"""
        cmd = [
            self.config.llama_binary_path,
            "-m", model_config.model_path,
            "--ctx-size", str(model_config.context_size),
            "--temp", str(model_config.temperature),
            "--top-p", str(model_config.top_p),
            "--top-k", str(model_config.top_k),
            "--min-p", str(model_config.min_p),
            "--port", "8080" if model_config == self.config.model_configs['ministral'] else "8081"
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def wait_for_server(self, port: int, timeout: int = 60):
        """Wait for server to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://localhost:{port}/health", timeout=2)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def start_servers(self):
        """Start both model servers in background threads"""
        def start_ministral():
            self.ministral_server = self.start_server(
                self.config.model_configs['ministral'],
                self.config.mmproj_path
            )
            if not self.wait_for_server(8080):
                logger.error("Ministral server failed to start")
                return
            logger.info("Ministral server started successfully")

        def start_devstral():
            self.devstral_server = self.start_server(self.config.model_configs['devstral'])
            if not self.wait_for_server(8081):
                logger.error("Devstral server failed to start")
                return
            logger.info("Devstral server started successfully")

        self.ministral_thread = threading.Thread(target=start_ministral, daemon=True)
        self.devstral_thread = threading.Thread(target=start_devstral, daemon=True)

        self.ministral_thread.start()
        self.devstral_thread.start()

        # Wait for both servers to start
        self.ministral_thread.join(timeout=60)
        self.devstral_thread.join(timeout=60)

    def execute_model(self, model_config: ModelConfig, prompt: str, port: int) -> str:
        """Execute model using existing server"""
        payload = {
            "model": "default",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": model_config.output_tokens,
            "temperature": model_config.temperature,
            "top_p": model_config.top_p,
            "top_k": model_config.top_k,
            "min_p": model_config.min_p
        }

        try:
            response = requests.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=payload,
                timeout=600
            )

            if response.status_code != 200:
                raise RuntimeError(f"Server error: {response.text}")

            return response.json()["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"Error communicating with model server: {e}")
            raise

    def execute_ministral(self, prompt: str) -> str:
        """Execute Ministral model"""
        return self.execute_model(
            model_config=self.config.model_configs['ministral'],
            prompt=prompt,
            port=8080
        )

    def execute_devstral(self, prompt: str) -> str:
        """Execute Devstral model"""
        return self.execute_model(
            model_config=self.config.model_configs['devstral'],
            prompt=prompt,
            port=8081
        )

    def shutdown(self):
        """Shutdown all model servers"""
        if self.ministral_server:
            self.ministral_server.terminate()
            try:
                self.ministral_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ministral_server.kill()

        if self.devstral_server:
            self.devstral_server.terminate()
            try:
                self.devstral_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.devstral_server.kill()

        logger.info("Model servers shutdown complete")
