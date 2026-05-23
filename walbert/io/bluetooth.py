"""
Bluetooth I/O layer implementation
"""

import subprocess
from typing import List, Optional
import serial
from .base import IOLayer

class BluetoothIOLayer(IOLayer):
    """Bluetooth I/O layer using rfcomm + pyserial"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.port = config.get("port", "/dev/rfcomm0")
        self.baudrate = config.get("baudrate", 9600)
        self.device: Optional[serial.Serial] = None

    def discover_devices(self) -> List[tuple]:
        """Discover nearby Bluetooth devices using bluetoothctl"""
        result = subprocess.run(
            ["bluetoothctl", "scan", "on"],
            capture_output=True,
            text=True,
            timeout=5
        )

        lines = result.stdout.splitlines()
        devices = []

        for line in lines:
            if "Device" in line:
                parts = line.split()
                address = parts[1]
                name = " ".join(parts[2:]) if len(parts) > 2 else "Unknown"
                devices.append((address, name))

        return devices

    def pair_device(self, address: str):
        """Pair and bind RFCOMM port"""
        # Pair
        subprocess.run(["bluetoothctl", "pair", address], check=False)
        subprocess.run(["bluetoothctl", "trust", address], check=False)
        subprocess.run(["bluetoothctl", "connect", address], check=False)

        # Bind RFCOMM
        subprocess.run(["sudo", "rfcomm", "bind", self.port, address, "1"], check=True)

        # Open serial port
        self.device = serial.Serial(self.port, self.baudrate, timeout=1)
        return self.device

    def read(self) -> str:
        if not self.device:
            raise RuntimeError("Bluetooth device not connected")

        data = self.device.readline()
        return data.decode("utf-8").strip()

    def write(self, text: str) -> None:
        if not self.device:
            raise RuntimeError("Bluetooth device not connected")

        self.device.write((text + "\n").encode("utf-8"))

    def disconnect(self):
        """Release RFCOMM and close serial port"""
        if self.device:
            self.device.close()
            self.device = None

        subprocess.run(["sudo", "rfcomm", "release", self.port], check=False)
