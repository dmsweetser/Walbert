"""
Model manager implementation using direct llama-completion binary execution
"""

import os
import re
import select
import subprocess
import logging
import time
from ..config import Config, ModelConfig

logger = logging.getLogger('walbert')

class ModelManager:
    """Manages model execution using llama-completion binary directly"""
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

    def execute_model(self, prompt: str, callback=None, interrupt_event=None) -> str:
        """Execute model using llama-completion binary with streaming support and interrupt capability"""
        model_config = self.config.model_configs['model']
        
        # Create temporary files for prompt and response
        ticks = int(time.time() * 1000)
        prompt_file = f"walbert_prompt_{ticks}.txt"
        response_file = f"walbert_response_{ticks}.txt"
        
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

        cmd = [
            self.config.llama_binary_path,
            "-m", model_config.model_path,
            "-f", prompt_file,
            "--temp", str(model_config.temperature),
            "--top-p", str(model_config.top_p),
            "--top-k", str(model_config.top_k),
            "--min-p", str(model_config.min_p),
            "-n", str(model_config.output_tokens),
            "--ctx-size", str(model_config.context_size),
            "--jinja",
            "--no-display-prompt",
            "-st"
        ]

        logger.info(f"Running llama-completion: {' '.join(cmd)}")
        # llama-completion writes model output to stderr, info to stderr too
        # Merge stderr into stdout so we can read everything from one pipe
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        response_content = ""
        raw_lines = []
        current_iteration = 0
        first_token = True
        # Pattern for llama-completion debug lines: "0.00.414.177 I ..."
        _debug_re = re.compile(r'^\d+\.\d+\.\d+\.\d+\s+[IEW]\s+')

        try:
            while True:
                if interrupt_event and interrupt_event.is_set():
                    logger.info("Model execution interrupted by user")
                    process.terminate()
                    process.wait()
                    break

                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if ready:
                    try:
                        line = process.stdout.readline()
                    except Exception:
                        line = ""

                    if not line:
                        # Check for EOF
                        if process.poll() is not None:
                            break
                        continue

                    raw_lines.append(line)

                    # Filter out debug lines
                    if not _debug_re.match(line):
                        response_content += line
                        current_iteration += 1

                        if callback and line.strip():
                            if first_token:
                                callback(f"{chr(10)}{chr(10)}[Walbert Output]{chr(10)}")
                                first_token = False
                            callback(line)
        except Exception as e:
            logger.error(f"Error during model execution: {e}")
        finally:
            process.wait()
            # Cleanup temp files
            if os.path.exists(prompt_file):
                os.remove(prompt_file)
            if os.path.exists(response_file):
                os.remove(response_file)

            if callback:
                callback(f"\n\n>>>>> ")

        return response_content

    def shutdown(self):
        """Shutdown model server (no-op for direct execution)"""
        logger.info("Model manager shutdown complete")