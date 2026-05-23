#!/usr/bin/env python3
"""
Unit tests for I/O layers
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walbert.io.console import ConsoleIOLayer
from walbert.io.serial import SerialIOLayer
from walbert.io.factory import IOLayerFactory, ChannelType

class TestIOLayers(unittest.TestCase):
    def test_console_io_read(self):
        with patch('builtins.input', return_value="test input"):
            io_layer = ConsoleIOLayer({})
            result = io_layer.read()
            self.assertEqual(result, "test input")

    def test_console_io_write(self):
        with patch('builtins.print') as mock_print:
            io_layer = ConsoleIOLayer({})
            io_layer.write("test output")
            mock_print.assert_called_once_with("test output")

    @patch('serial.Serial')
    @patch('serial.tools.list_ports.comports')
    def test_serial_io_detect_ports(self, mock_comports, mock_serial):
        mock_comports.return_value = [MagicMock(device="/dev/ttyUSB0")]
        io_layer = SerialIOLayer({})
        ports = io_layer.detect_ports()
        self.assertEqual(ports, ["/dev/ttyUSB0"])

    @patch('serial.Serial')
    def test_serial_io_connect(self, mock_serial):
        io_layer = SerialIOLayer({})
        io_layer.connect("/dev/ttyUSB0")
        mock_serial.assert_called_once_with("/dev/ttyUSB0", 9600)

    @patch('serial.Serial')
    def test_serial_io_read(self, mock_serial):
        mock_serial_instance = MagicMock()
        mock_serial_instance.readline.return_value = b"test output\n"
        mock_serial.return_value = mock_serial_instance
        io_layer = SerialIOLayer({})
        io_layer.connect("/dev/ttyUSB0")
        result = io_layer.read()
        self.assertEqual(result, "test output")

    @patch('serial.Serial')
    def test_serial_io_write(self, mock_serial):
        mock_serial_instance = MagicMock()
        mock_serial.return_value = mock_serial_instance
        io_layer = SerialIOLayer({})
        io_layer.connect("/dev/ttyUSB0")
        io_layer.write("test input")
        mock_serial_instance.write.assert_called_once_with(b"test input")

    def test_factory_create_console(self):
        io_layer = IOLayerFactory.create_io_layer(ChannelType.CONSOLE, {})
        self.assertIsInstance(io_layer, ConsoleIOLayer)

    def test_factory_create_serial(self):
        io_layer = IOLayerFactory.create_io_layer(ChannelType.SERIAL, {})
        self.assertIsInstance(io_layer, SerialIOLayer)

    def test_factory_invalid_channel(self):
        with self.assertRaises(ValueError):
            IOLayerFactory.create_io_layer(ChannelType(999), {})

if __name__ == '__main__':
    unittest.main()
