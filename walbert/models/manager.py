"""
Model manager implementation
"""

import os
import subprocess
import logging
from typing import Optional
import requests
from ..config import Config

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

        for model_name, model_path in self.config.model_paths.items():
            if not os.path.isfile(model_path):
                raise FileNotFoundError(f"{model_name} model not found at {model_path}")

    def execute_model(self, model_path: str, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute model through llama.cpp server binary with multimodal support"""
        cmd = [
            self.config.llama_binary_path,
            "-m", model_path,
            "--ctx-size", "2048",
            "--temp", "0.7"
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")
        server = subprocess.Popen(cmd)

        try:
            # Wait for server to start
            import time
            time.sleep(5)

            # Now send the prompt via the OpenAI-compatible API
            payload = {
                "model": "default",
                "messages": [{"role": "user", "content": prompt}]
            }
            response = requests.post("http://localhost:8080/v1/chat/completions", json=payload, timeout=30)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error executing model: {e}")
            raise
        finally:
            server.terminate()

    def execute_ministral(self, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute Ministral model"""
        mmproj_path = mmproj_path or self.config.model_paths.get('mmproj')
        return self.execute_model(
            model_path=self.config.model_paths['primary'],
            prompt=prompt,
            mmproj_path=mmproj_path
        )

    def execute_devstral(self, prompt: str) -> str:
        """Execute Devstral model"""
        return self.execute_model(
            model_path=self.config.model_paths['devstral'],
            prompt=prompt
        )
