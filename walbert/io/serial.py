"""
Serial I/O layer implementation
"""

import serial
import serial.tools.list_ports
from typing import Optional
from .base import IOLayer

class SerialIOLayer(IOLayer):
    """Serial communication I/O layer"""
    def __init__(self, config: dict):
        super().__init__(config)
        self.port = config.get('port')
        self.baudrate = config.get('baudrate', 9600)
        self.serial_conn = None

    def connect(self, port: Optional[str] = None):
        """Connect to serial device"""
        port = port or self.port or self.detect_ports()[0]
        self.serial_conn = serial.Serial(port, self.baudrate)
        return f"Connected to serial device on {port}"

    def detect_ports(self) -> list:
        """Detect available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def read(self) -> str:
        if not self.serial_conn:
            raise RuntimeError("Serial connection not established")
        return self.serial_conn.readline().decode('utf-8').strip()

    def write(self, text: str) -> None:
        if not self.serial_conn:
            raise RuntimeError("Serial connection not established")
        self.serial_conn.write(text.encode('utf-8'))

    def close(self):
        """Close serial connection"""
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
