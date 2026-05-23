"""
Console I/O layer implementation
"""

from .base import IOLayer

class ConsoleIOLayer(IOLayer):
    """Console-based I/O layer"""
    def read(self) -> str:
        return input("> ")

    def write(self, text: str) -> None:
        print(text)
