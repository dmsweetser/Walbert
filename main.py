#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import sys
import os
import json
import logging
import sqlite3
import subprocess
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum, auto
import tempfile
import re
import importlib
import inspect
from urllib import request
import usb.core
import serial
import serial.tools.list_ports
import requests

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('walbert.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('walbert')

@dataclass
class Config:
    """System configuration"""
    model_paths: Dict[str, str]
    llama_binary_path: str
    log_level: str

@dataclass
class IOConfig:
    """I/O layer configuration"""
    io_layers: Dict[str, Dict[str, Any]]

class ChannelType(Enum):
    """Supported input/output channels"""
    CONSOLE = auto()
    SERIAL = auto()
    BLUETOOTH = auto()
    USB = auto()
    PYTHON_CODE = auto()

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

    def requires_authorization(self) -> bool:
        """Check if the layer requires user authorization"""
        return self.config.get('require_authorization', False)

class ConsoleIOLayer(IOLayer):
    """Console-based I/O layer"""
    def read(self) -> str:
        return input("> ")

    def write(self, text: str) -> None:
        print(text)

class SerialIOLayer(IOLayer):
    """Serial communication I/O layer"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.port = config.get('port')
        self.baudrate = config.get('baudrate', 9600)
        self.serial_conn = None

    def connect(self, port: Optional[str] = None):
        """Connect to serial device"""
        port = port or self.port or self.detect_ports()[0]
        self.serial_conn = serial.Serial(port, self.baudrate)
        logger.info(f"Connected to serial device on {port}")

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
            
class BluetoothIOLayer:
    """Bluetooth I/O layer using rfcomm + pyserial"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
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

class PythonCodeIOLayer(IOLayer):
    """Python code execution I/O layer"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.sandbox_dir = tempfile.mkdtemp(prefix='walbert_sandbox_')

    def execute_code(self, code: str, args: list = None) -> str:
        """Execute Python code in sandboxed environment"""
        args = args or []
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', dir=self.sandbox_dir) as f:
            f.write(code)
            f.flush()

            result = subprocess.run(
                ['python3', f.name] + args,
                capture_output=True,
                text=True,
                cwd=self.sandbox_dir
            )

            # Clean up
            os.unlink(f.name)

            return result.stdout

    def write(self, text: str) -> None:
        """Write output (not used for code execution layer)"""
        print(text)

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

class ModelManager:
    """Manages model execution through llama.cpp binaries"""
    def __init__(self, config: Config):
        self.config = config
        self.validate_binaries()

    def validate_binaries(self):
        """Validate that all required binaries exist"""
        if not os.path.isfile(self.config.llama_binary_path):
            raise FileNotFoundError(f"llama.cpp binary not found at {self.config.llama_binary_path}")

        for model_name, model_path in self.config.model_paths.items():
            if not os.path.isfile(model_path):
                raise FileNotFoundError(f"{model_name} model not found at {model_path}")

    def execute_model(self, model_path: str, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute model through llama.cpp server binary with multimodal support"""
        cmd = [
            self.config.llama_binary_path,
            "-m", model_path,
            "--ctx-size", "2048",
            "--temp", "0.7"
        ]

        if mmproj_path:
            cmd.extend(["--mmproj", mmproj_path])

        logger.info(f"Starting llama-server: {' '.join(cmd)}")
        server = subprocess.Popen(cmd)

        # Now send the prompt via the OpenAI-compatible API
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post("http://localhost:8080/v1/chat/completions", json=payload)
        server.terminate()

        return response.json()["choices"][0]["message"]["content"]


    def execute_ministral(self, prompt: str, mmproj_path: Optional[str] = None) -> str:
        """Execute Ministral model"""
        mmproj_path = mmproj_path or self.config.model_paths.get('mmproj')
        return self.execute_model(
            model_path=self.config.model_paths['primary'],
            prompt=prompt,
            mmproj_path=mmproj_path
        )

    def execute_devstral(self, prompt: str) -> str:
        """Execute Devstral model"""
        return self.execute_model(
            model_path=self.config.model_paths['devstral'],
            prompt=prompt
        )

class DatabaseManager:
    """Manages SQLite database operations"""
    def __init__(self, db_path: str = "walbert.db"):
        self.db_path = db_path
        self.connect()

    def connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.init_schema()

    def init_schema(self):
        """Initialize database schema"""
        # Items table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                content TEXT,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tags table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        """)

        # Item-tags mapping
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_tags (
                item_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id),
                PRIMARY KEY (item_id, tag_id)
            )
        """)

        # Conversations table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                summary TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                channel TEXT
            )
        """)

        # Messages table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER,
                content TEXT,
                sender TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        self.conn.commit()

    def store_item(self, content: str, tags: list, item_type: str = "text") -> int:
        """Store an item with tags"""
        self.cursor.execute(
            "INSERT INTO items (content, type) VALUES (?, ?)",
            (content, item_type)
        )
        item_id = self.cursor.lastrowid

        for tag in tags:
            # Add tag if it doesn't exist
            self.cursor.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                (tag,)
            )
            # Link item to tag
            self.cursor.execute("""
                INSERT INTO item_tags (item_id, tag_id)
                VALUES (?, (SELECT id FROM tags WHERE name = ?))
            """, (item_id, tag))

        self.conn.commit()
        return item_id

    def retrieve_items_by_tag(self, tag: str) -> list:
        """Retrieve items by tag"""
        self.cursor.execute("""
            SELECT i.id, i.content, i.type, i.created_at
            FROM items i
            JOIN item_tags it ON i.id = it.item_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
        """, (tag,))
        return self.cursor.fetchall()

    def retrieve_items_by_multiple_tags(self, tags: list) -> list:
        """Retrieve items by multiple tags (AND logic)"""
        placeholders = ','.join(['?'] * len(tags))
        self.cursor.execute(f"""
            SELECT i.id, i.content, i.type, i.created_at
            FROM items i
            JOIN item_tags it ON i.id = it.item_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name IN ({placeholders})
            GROUP BY i.id
            HAVING COUNT(DISTINCT t.name) = {len(tags)}
        """, tags)
        return self.cursor.fetchall()

    def start_conversation(self, channel: str) -> int:
        """Start a new conversation"""
        self.cursor.execute(
            "INSERT INTO conversations (channel) VALUES (?)",
            (channel,)
        )
        return self.cursor.lastrowid

    def add_message(self, conversation_id: int, content: str, sender: str = "user") -> int:
        """Add a message to a conversation"""
        self.cursor.execute(
            "INSERT INTO messages (conversation_id, content, sender) VALUES (?, ?, ?)",
            (conversation_id, content, sender)
        )
        return self.cursor.lastrowid

    def end_conversation(self, conversation_id: int, summary: str):
        """End a conversation"""
        self.cursor.execute(
            "UPDATE conversations SET end_time = CURRENT_TIMESTAMP, summary = ? WHERE id = ?",
            (summary, conversation_id)
        )
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()

class SkillManager:
    """Manages skill execution"""
    def __init__(self, db: DatabaseManager):
        self.db = db

    def store_skill(self, name: str, code: str, tags: list) -> int:
        """Store a new skill"""
        tags = tags + ["skill", name]
        return self.db.store_item(code, tags, item_type="skill")

    def retrieve_skill(self, name: str) -> Optional[str]:
        """Retrieve a skill by name"""
        items = self.db.retrieve_items_by_multiple_tags(["skill", name])
        if items:
            return items[0][1]  # Return content
        return None

    def execute_skill(self, skill_code: str, args: list = None) -> str:
        """Execute a skill in sandboxed environment"""
        args = args or []
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(skill_code)
            f.flush()

            result = subprocess.run(
                ['python3', f.name] + args,
                capture_output=True,
                text=True
            )

            return result.stdout

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_patterns = {
            "response": r"~walbert_response_start~\n(.*?)\n~walbert_response_end~",
            "channel": r"~walbert_response_channel_start~\n(.*?)\n~walbert_response_channel_end~",
            "should_call_smarter_cousin": r"~walbert_should_call_smarter_cousin_start~\n(.*?)\n~walbert_should_call_smarter_cousin_end~",
            "should_query_datastore": r"~walbert_should_query_datastore_start~\n(.*?)\n~walbert_should_query_datastore_end~",
            "should_execute_skill": r"~walbert_should_execute_skill_start~\n(.*?)\n~walbert_should_execute_skill_end~",
            "should_store_memory": r"~walbert_should_store_memory_start~\n(.*?)\n~walbert_should_store_memory_end~",
            "conversation_complete": r"~walbert_conversation_complete_start~\n(.*?)\n~walbert_conversation_complete_end~",
            "db_command": r"~walbert_db_command_start~\n(.*?)\n(.*?)\n~walbert_db_command_end~",
            "skill_execution": r"~walbert_skill_execution_start~\n(.*?)\n(.*?)\n~walbert_skill_execution_end~",
            "memory_storage": r"~walbert_memory_storage_start~\n(.*?)\n(.*?)\n~walbert_memory_storage_end~",
            "hardware_action": r"~walbert_hardware_action_start~\n(.*?)\n~walbert_hardware_action_end~"
        }

    def parse_response(self, response_text: str) -> dict:
        """Parse response text into structured data"""
        parsed = {}
        for key, pattern in self.block_patterns.items():
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                if key in ["db_command", "skill_execution", "memory_storage", "hardware_action"]:
                    parsed[key] = {
                        "command": match.group(1).strip(),
                        "args": json.loads(match.group(2).strip()) if match.group(2).strip() else {}
                    }
                else:
                    parsed[key] = match.group(1).strip()
        return parsed

class AuthorizationManager:
    """Handles user authorization for sensitive operations"""
    @staticmethod
    def request_authorization(layer_name: str, action_description: str) -> bool:
        """Request user authorization for an action"""
        print(f"\n[Authorization Request]")
        print(f"Layer: {layer_name}")
        print(f"Action: {action_description}")
        print("Do you authorize this action? (yes/no): ", end="")
        response = input().strip().lower()
        return response == "yes"

class WalbertAgent:
    """Main Walbert agent class"""
    SYSTEM_PROMPT = """
    You are Walbert, a local-first AI agent built on llama.cpp.
    Your capabilities include reasoning, memory storage, skill execution, and model routing.

    ## Core Directives
    1. **Local-First**: Operate entirely on local llama.cpp binaries.
    2. **Protocol Compliance**: Use walbert_ blocks for all decisions and actions.
    3. **Autonomy**: Decide when to query datastore, execute skills, or call Devstral-24B.
    4. **Memory**: Store relevant information with appropriate tags.
    5. **Safety**: Never execute untrusted code or access external resources.

    ## Decision Flow
    1. Evaluate if datastore query is needed (~walbert_should_query_datastore~).
    2. Evaluate if skill execution is needed (~walbert_should_execute_skill~).
    3. Evaluate if Devstral-24B should be called (~walbert_should_call_smarter_cousin~).
    4. Evaluate if memory should be stored (~walbert_should_store_memory~).
    5. Emit final response (~walbert_response~).

    ## Available Blocks
    - Decision: should_call_smarter_cousin, should_query_datastore, should_execute_skill, should_store_memory, conversation_complete
    - Action: db_command, skill_execution, memory_storage, hardware_action
    - Core: response, response_channel

    ## Example
    ~walbert_should_query_datastore_start~
    YES
    ~walbert_should_query_datastore_end~
    ~walbert_db_command_start~
    RETRIEVE_ITEMS
    {"tags": ["example"]}
    ~walbert_db_command_end~
    ~walbert_response_start~
    Here is the retrieved data.
    ~walbert_response_end~
    ~walbert_response_channel_start~
    console
    ~walbert_response_channel_end~
    """

    def __init__(self, config: Config, io_config: IOConfig):
        self.config = config
        self.io_config = io_config
        self.model_manager = ModelManager(config)
        self.db = DatabaseManager()
        self.skill_manager = SkillManager(self.db)
        self.response_parser = ResponseParser()
        self.authorization_manager = AuthorizationManager()
        self.io_factory = IOLayerFactory()
        self.current_conversation_id = None

    def load_io_layer(self, channel_type: ChannelType) -> IOLayer:
        """Load I/O layer with proper configuration"""
        layer_name = channel_type.name.lower()
        if layer_name not in self.io_config.io_layers:
            raise ValueError(f"Unknown I/O layer: {layer_name}")

        layer_config = self.io_config.io_layers[layer_name]
        if not layer_config.get('enabled', False):
            raise ValueError(f"I/O layer {layer_name} is disabled")

        return self.io_factory.create_io_layer(channel_type, layer_config)

    def handle_input_channel(self, channel_type: ChannelType) -> str:
        """Handle input from a specific channel"""
        try:
            io_layer = self.load_io_layer(channel_type)

            if io_layer.requires_authorization():
                if not self.authorization_manager.request_authorization(
                    channel_type.name.lower(),
                    "Reading input"
                ):
                    return ""

            return io_layer.read()

        except Exception as e:
            logger.error(f"Error reading from {channel_type.name}: {e}")
            return ""

    def handle_hardware_interaction(self, hardware_action: dict) -> Optional[str]:
        """Handle hardware interaction requests"""
        peripheral_type = hardware_action.get("peripheral_type")
        action = hardware_action.get("action")
        data = hardware_action.get("data", {})

        try:
            if peripheral_type == "serial":
                io_layer = self.load_io_layer(ChannelType.SERIAL)
                if action == "connect":
                    port = data.get("port")
                    baudrate = data.get("baudrate", 9600)
                    io_layer.connect(port or io_layer.detect_ports()[0])
                    return f"Connected to {port or 'default'} serial port"
                elif action == "read":
                    return io_layer.read()
                elif action == "write":
                    text = data.get("data", "")
                    io_layer.write(text)
                    return f"Wrote to serial: {text}"

            elif peripheral_type == "bluetooth":
                io_layer = self.load_io_layer(ChannelType.BLUETOOTH)
                if action == "discover":
                    devices = io_layer.discover_devices()
                    return f"Found devices: {devices}"
                elif action == "pair":
                    address = data.get("address")
                    sock = io_layer.pair_device(address)
                    return f"Paired with {address}"
                elif action == "read":
                    sock = data.get("sock")
                    return io_layer.read(sock)
                elif action == "write":
                    sock = data.get("sock")
                    text = data.get("data", "")
                    io_layer.write(sock, text)
                    return f"Wrote to Bluetooth: {text}"

            elif peripheral_type == "usb":
                io_layer = self.load_io_layer(ChannelType.USB)
                if action == "detect":
                    devices = io_layer.detect_devices()
                    return f"Found USB devices: {devices}"
                elif action == "connect":
                    vendor_id = data.get("vendor_id")
                    product_id = data.get("product_id")
                    dev = io_layer.connect(vendor_id, product_id)
                    return f"Connected to USB device {vendor_id}:{product_id}"
                elif action == "read":
                    dev = data.get("dev")
                    endpoint = data.get("endpoint", 0x81)
                    size = data.get("size", 64)
                    return io_layer.read(dev, endpoint, size)
                elif action == "write":
                    dev = data.get("dev")
                    data_bytes = data.get("data", b"")
                    endpoint = data.get("endpoint", 0x01)
                    io_layer.write(dev, data_bytes, endpoint)
                    return f"Wrote to USB device"

        except Exception as e:
            logger.error(f"Hardware interaction failed: {e}")
            return f"Error: {e}"

    def process_response(self, response_text: str, input_channel: ChannelType) -> str:
        """Process model response and execute actions"""
        parsed = self.response_parser.parse_response(response_text)

        # Store message in database
        if self.current_conversation_id:
            self.db.add_message(self.current_conversation_id, response_text, "assistant")

        # Execute actions
        if parsed.get("should_query_datastore") == "YES":
            db_command = parsed.get("db_command", {})
            if db_command["command"] == "RETRIEVE_ITEMS":
                tags = db_command["args"].get("tags", [])
                if tags:
                    results = self.db.retrieve_items_by_multiple_tags(tags)
                    response_text += f"\n\nDatastore Results: {results}"

        if parsed.get("should_execute_skill") == "YES":
            skill_exec = parsed.get("skill_execution", {})
            skill_name = skill_exec["args"].get("skill_name")
            args = skill_exec["args"].get("args", [])

            if skill_name:
                skill_code = self.skill_manager.retrieve_skill(skill_name)
                if skill_code:
                    try:
                        result = self.skill_manager.execute_skill(skill_code, args)
                        response_text += f"\n\nSkill Result: {result}"
                    except Exception as e:
                        response_text += f"\n\nSkill Execution Error: {e}"
                else:
                    response_text += f"\n\nError: Skill '{skill_name}' not found"

        if parsed.get("should_store_memory") == "YES":
            memory = parsed.get("memory_storage", {})
            content = memory["args"].get("content", "")
            tags = memory["args"].get("tags", [])

            if content and tags:
                self.db.store_item(content, tags)
                response_text += "\n\nMemory stored successfully"

        if parsed.get("hardware_action") is not None:
            hardware_action = parsed["hardware_action"]
            result = self.handle_hardware_interaction(hardware_action)
            if result:
                response_text += f"\n\nHardware Result: {result}"

        return response_text

    def emit_input_channel(self, channel: ChannelType) -> str:
        """Emit the input channel block for context"""
        return f"""~walbert_input_channel_start~
{channel.name.lower()}
~walbert_input_channel_end~
"""

    def start_conversation(self, channel: ChannelType):
        """Start a new conversation"""
        self.current_conversation_id = self.db.start_conversation(channel.name.lower())
        self.db.add_message(self.current_conversation_id, self.SYSTEM_PROMPT, "system")

    def end_conversation(self):
        """End current conversation"""
        if self.current_conversation_id:
            summary = "End of conversation"
            self.db.end_conversation(self.current_conversation_id, summary)
            self.current_conversation_id = None

    def run(self):
        """Main agent execution loop"""
        print("Welcome to Walbert! Type 'exit' to quit.")

        # Start initial conversation
        self.start_conversation(ChannelType.CONSOLE)

        while True:
            try:
                # Read input
                user_input = self.handle_input_channel(ChannelType.CONSOLE)
                if user_input.lower() in ['exit', 'quit']:
                    break

                # Store user message
                if self.current_conversation_id:
                    self.db.add_message(self.current_conversation_id, user_input)

                # Build full prompt
                full_prompt = self.SYSTEM_PROMPT + "\n\n" + self.emit_input_channel(ChannelType.CONSOLE) + "\nUser: " + user_input

                # Process until conversation is complete
                conversation_active = True
                response_text = ""

                while conversation_active:
                    # Execute model
                    model_response = self.model_manager.execute_ministral(user_input)
                    response_text = self.process_response(model_response, ChannelType.CONSOLE)

                    # Parse response
                    parsed = self.response_parser.parse_response(response_text)

                    # Check if conversation should continue
                    if parsed.get("conversation_complete") == "YES":
                        conversation_active = False

                    # Update full prompt with response
                    full_prompt += f"\n\nAssistant: {response_text}"

                # Output final response
                if response_text:
                    print(response_text)

                # Check if conversation should end
                parsed = self.response_parser.parse_response(response_text)
                if parsed.get("conversation_complete") == "YES":
                    self.end_conversation()
                    print("\nConversation ended.")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                self.end_conversation()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"An error occurred: {e}")

def load_config() -> Config:
    """Load system configuration"""
    try:
        with open('config.json', 'r') as f:
            config_data = json.load(f)
            return Config(
                model_paths=config_data['model_paths'],
                llama_binary_path=config_data['llama_binary_path'],
                log_level=config_data['log_level']
            )
    except FileNotFoundError:
        logger.error("config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def load_io_config() -> IOConfig:
    """Load I/O configuration"""
    try:
        with open('io_config.json', 'r') as f:
            io_config_data = json.load(f)
            return IOConfig(io_config_data)
    except FileNotFoundError:
        logger.error("io_config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading I/O config: {e}")
        sys.exit(1)

def main():
    """Main entry point"""
    # Load configurations
    config = load_config()
    io_config = load_io_config()

    # Set log level
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create and run agent
    agent = WalbertAgent(config, io_config)
    agent.run()

if __name__ == "__main__":
    main()
