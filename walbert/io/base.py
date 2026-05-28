"""
Base I/O layer class
"""

from typing import Dict, Any

class IOLayer:
    """Base class for I/O layers"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def read(self) -> str:
        """Read input from the channel"""
        raise NotImplementedError

    def write(self, text: str) -> None:
        """Write output to the channel"""
        raise NotImplementedError

    def is_enabled(self) -> bool:
        """Check if the layer is enabled"""
        return self.config.get('enabled', False)