"""
I/O layer factory implementation
"""

from enum import Enum, auto
from typing import Dict, Any
from .base import IOLayer
from .console import ConsoleIOLayer
from .serial import SerialIOLayer

class ChannelType(Enum):
    """Supported input/output channels"""
    CONSOLE = "console"
    SERIAL = "serial"

class IOLayerFactory:
    """Factory for creating I/O layer instances"""
    @staticmethod
    def create_io_layer(channel_type: ChannelType, config: Dict[str, Any]) -> IOLayer:
        """Create I/O layer instance based on channel type"""
        if channel_type == ChannelType.CONSOLE:
            return ConsoleIOLayer(config)
        elif channel_type == ChannelType.SERIAL:
            return SerialIOLayer(config)
        else:
            raise ValueError(f"Unsupported channel type: {channel_type}")
