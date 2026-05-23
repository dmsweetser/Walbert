"""
Model manager implementation
"""

import os
import subprocess
import logging
from typing import Optional, Dict
from ..config import Config, ModelConfig

logger = logging.getLogger('walbert')

class ModelManager:
    """Manages model execution through llama.cpp binaries"""
    def __init__(self, config: Config):
        self.config = config
        self.validate_binaries()

    def validate_binaries(self):
        """Validate that all required binaries exist"""
        if not os.path.isfile(self.config.llama_binary_path):
            raise FileNotFoundError(f"llama.cpp binary not found at {self.config.llama_binary_path}")

        for model_name, model_config in self.config.model_configs.items():
            if not os.path.isfile(model_config.model_path):
                raise FileNotFoundError(f"{model_name} model not found at {model_config.model_path}")

    def execute_model(self, model_config: ModelConfig, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute model using llama.cpp's llama-server with multimodal support"""

        # Start llama-server
        cmd = [
            self.config.llama_binary_path,  # now points to llama-server
            "-m", model_config.model_path,
            "--ctx-size", str(model_config.context_size),
            "--temp", str(model_config.temperature),
            "--top-p", str(model_config.top_p),
            "--top-k", str(model_config.top_k),
            "--min-p", str(model_config.min_p),
            "--port", "8080"
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")

        # Start server as background process
        server = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            # Wait for server to be ready
            import time, requests
            for _ in range(50):
                try:
                    requests.get("http://localhost:8080/health")
                    break
                except Exception:
                    time.sleep(2)
            else:
                raise RuntimeError("llama-server did not start in time")

            # Build OpenAI-compatible request
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

            logger.info("Sending prompt to llama-server API")
            response = requests.post(
                "http://localhost:8080/v1/chat/completions",
                json=payload,
                timeout=600
            )

            if response.status_code != 200:
                raise RuntimeError(f"Server error: {response.text}")

            return response.json()["choices"][0]["message"]["content"]

        finally:
            # Clean shutdown
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    def execute_ministral(self, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute Ministral model"""
        return self.execute_model(
            model_config=self.config.model_configs['ministral'],
            prompt=prompt,
            mmproj_path=mmproj_path
        )

    def execute_devstral(self, prompt: str) -> str:
        """Execute Devstral model"""
        return self.execute_model(
            model_config=self.config.model_configs['devstral'],
            prompt=prompt
        )
