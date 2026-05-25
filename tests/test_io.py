"""
Test cases for I/O layers
"""

import unittest
from unittest.mock import patch, MagicMock
from walbert.io.factory import IOLayerFactory, ChannelType
from walbert.io.console import ConsoleIOLayer
from walbert.io.serial import SerialIOLayer
from walbert.io.python_code import PythonCodeIOLayer

class TestIOLayerFactory(unittest.TestCase):
    def test_create_console_layer(self):
        config = {"enabled": True, "require_authorization": False}
        layer = IOLayerFactory.create_io_layer(ChannelType.CONSOLE, config)
        self.assertIsInstance(layer, ConsoleIOLayer)

    def test_create_serial_layer(self):
        config = {"enabled": True, "require_authorization": False, "port": "/dev/ttyUSB0"}
        layer = IOLayerFactory.create_io_layer(ChannelType.SERIAL, config)
        self.assertIsInstance(layer, SerialIOLayer)

    def test_create_python_code_layer(self):
        config = {"enabled": True, "require_authorization": False}
        layer = IOLayerFactory.create_io_layer(ChannelType.PYTHON_CODE, config)
        self.assertIsInstance(layer, PythonCodeIOLayer)

class TestConsoleIOLayer(unittest.TestCase):
    def setUp(self):
        self.config = {"enabled": True, "require_authorization": False}
        self.layer = ConsoleIOLayer(self.config)

    @patch('builtins.input', return_value="test input")
    def test_read(self, mock_input):
        result = self.layer.read()
        self.assertEqual(result, "test input")

    @patch('builtins.print')
    def test_write(self, mock_print):
        self.layer.write("test output")
        mock_print.assert_called_once_with("test output")

class TestSerialIOLayer(unittest.TestCase):
    def setUp(self):
        self.config = {"enabled": True, "require_authorization": False, "port": "/dev/ttyUSB0"}
        self.layer = SerialIOLayer(self.config)

    @patch('serial.Serial')
    def test_connect(self, mock_serial):
        mock_serial.return_value = MagicMock()
        result = self.layer.connect()
        self.assertEqual(result, "Connected to serial device on /dev/ttyUSB0")

    @patch('serial.Serial')
    def test_read(self, mock_serial):
        mock_serial_instance = MagicMock()
        mock_serial_instance.readline.return_value = b"test data\n"
        mock_serial.return_value = mock_serial_instance
        self.layer.serial_conn = mock_serial_instance

        result = self.layer.read()
        self.assertEqual(result, "test data")

    @patch('serial.Serial')
    def test_write(self, mock_serial):
        mock_serial_instance = MagicMock()
        mock_serial.return_value = mock_serial_instance
        self.layer.serial_conn = mock_serial_instance

        self.layer.write("test data")
        mock_serial_instance.write.assert_called_once_with(b"test data")

class TestPythonCodeIOLayer(unittest.TestCase):
    def setUp(self):
        self.config = {"enabled": True, "require_authorization": False}
        self.layer = PythonCodeIOLayer(self.config)

    @patch('subprocess.run')
    def test_execute_code(self, mock_run):
        mock_run.return_value = MagicMock(stdout="test output", returncode=0)
        result = self.layer.execute_code("print('test')")
        self.assertEqual(result, "test output")

if __name__ == "__main__":
    unittest.main()
