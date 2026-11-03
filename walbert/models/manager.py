"""
Model manager - uses llama-server as a persistent background process.

Replaces the old llama-completion binary approach with a persistent
llama-server that keeps KV cache in memory for fast subsequent calls.
"""

import logging
from walbert.models.llama_server import LlamaServerManager

logger = logging.getLogger('walbert')


class ModelManager:
    """Manages model execution via llama-server HTTP API."""

    def __init__(self, config):
        self.config = config
        self.server = LlamaServerManager(config)
        self.server.start()

    def execute_model(self, prompt: str, callback=None, interrupt_event=None) -> str:
        """Execute model via llama-server HTTP API."""
        return self.server.execute_model(prompt, callback, interrupt_event)

    def shutdown(self):
        """Shutdown llama-server."""
        self.server.shutdown()
