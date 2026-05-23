"""
USB I/O layer implementation
"""

import usb.core
from .base import IOLayer

class USBIOLayer(IOLayer):
    """USB I/O layer"""
    def detect_devices(self) -> list:
        """Detect connected USB devices"""
        devices = usb.core.find(find_all=True)
        return [(dev.idVendor, dev.idProduct) for dev in devices]

    def connect(self, vendor_id: int, product_id: int):
        """Connect to USB device"""
        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if dev is None:
            raise ValueError("Device not found")
        return dev

    def read(self, dev, endpoint: int = 0x81, size: int = 64) -> bytes:
        """Read from USB device"""
        return dev.read(endpoint, size).tobytes()

    def write(self, dev, data: bytes, endpoint: int = 0x01) -> None:
        """Write to USB device"""
        dev.write(endpoint, data)
