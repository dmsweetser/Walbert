"""
I/O layer factory implementation
"""

from enum import Enum, auto
from typing import Dict, Any
from .base import IOLayer
from .console import ConsoleIOLayer
from .serial import SerialIOLayer
from .bluetooth import BluetoothIOLayer
from .usb import USBIOLayer
from .python_code import PythonCodeIOLayer

class ChannelType(Enum):
    """Supported input/output channels"""
    CONSOLE = "console"
    SERIAL = "serial"
    BLUETOOTH = "bluetooth"
    USB = "usb"
    PYTHON_CODE = "python_code"

class IOLayerFactory:
    """Factory for creating I/O layer instances"""
    @staticmethod
    def create_io_layer(channel_type: ChannelType, config: Dict[str, Any]) -> IOLayer:
        """Create I/O layer instance based on channel type"""
        if channel_type == ChannelType.CONSOLE:
            return ConsoleIOLayer(config)
        elif channel_type == ChannelType.SERIAL:
            return SerialIOLayer(config)
        elif channel_type == ChannelType.BLUETOOTH:
            return BluetoothIOLayer(config)
        elif channel_type == ChannelType.USB:
            return USBIOLayer(config)
        elif channel_type == ChannelType.PYTHON_CODE:
            return PythonCodeIOLayer(config)
        else:
            raise ValueError(f"Unsupported channel type: {channel_type}")
