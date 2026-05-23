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
        """Execute model through llama.cpp binary with direct CLI execution"""
        cmd = [
            self.config.llama_binary_path,
            "-m", model_config.model_path,
            "--ctx-size", str(model_config.context_size),
            "--temp", str(model_config.temperature),
            "--top-p", str(model_config.top_p),
            "--top-k", str(model_config.top_k),
            "--min-p", str(model_config.min_p),
            "-p", prompt,
            "-n", str(model_config.output_tokens)
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Executing model: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Model execution failed: {result.stderr}")
            raise RuntimeError(f"Model execution failed: {result.stderr}")

        return result.stdout

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
