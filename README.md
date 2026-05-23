# Walbert
A local-first, console-based AI agentic framework built on llama.cpp

## Overview
Walbert is a fully local AI agent that runs entirely on your machine using llama.cpp compiled binaries. It provides:

- Local-only execution with no external dependencies
- Multiple model support (Ministral-3B, Devstral-24B)
- Unified I/O layer with support for console, serial, Bluetooth, and USB
- SQLite-based datastore with tag-based retrieval
- Skill system for extensible capabilities
- Hardware interaction support

## Installation

### Prerequisites
- Linux system
- Python 3
- Git
- wget
- tar

### Quick Start
```bash
./install.sh
```

This will:
1. Create a Python virtual environment
2. Install dependencies
3. Download required models and binaries
4. Create default configuration files

## Usage

### Starting Walbert
```bash
source venv/bin/activate
python3 main.py
```

### Configuration
Walbert uses two configuration files:

- `config.json`: Main system configuration
- `io_config.json`: I/O layer configuration

Both files are created automatically during installation.

## Features

### Core Capabilities
- **Local Execution**: Runs entirely on your machine
- **Multi-Model**: Uses Ministral-3B for primary reasoning and Devstral-24B for complex tasks
- **Unified I/O**: Supports multiple input/output channels
- **Skill System**: Store and execute Python-based skills
- **Hardware Integration**: USB, serial, and Bluetooth support

### I/O Layers
Walbert supports multiple I/O layers that can be configured to be enabled, disabled, or require user authorization:

- **Console**: Default text-based interface
- **Serial**: Bidirectional serial communication
- **Bluetooth**: Bluetooth device discovery and pairing
- **USB**: USB device detection and communication
- **Python Code**: Safe execution of Python code with authorization

## Architecture

### System Components
1. **Model Execution**: Handles llama.cpp binary execution
2. **I/O Layer**: Manages all input/output channels
3. **Datastore**: SQLite-based storage for items, memories, and conversations
4. **Skill System**: Sandboxed execution of Python skills
5. **Configuration**: Centralized configuration management

### Data Flow
1. Input is received through configured I/O layer
2. Input is processed by the primary model (Ministral-3B)
3. Model may query datastore, execute skills, or route to Devstral-24B
4. Response is formatted using Walbert's response protocol
5. Output is sent through appropriate I/O layer

## Configuration

### config.json
```json
{
    "model_paths": {
        "primary": "models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        "mmproj": "models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf",
        "devstral": "models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    },
    "llama_binary_path": "llama.cpp/bin/llama-server",
    "log_level": "INFO"
}
```

### io_config.json
```json
{
    "io_layers": {
        "console": {
            "enabled": true,
            "require_authorization": false
        },
        "serial": {
            "enabled": false,
            "require_authorization": true
        },
        "bluetooth": {
            "enabled": false,
            "require_authorization": true
        },
        "usb": {
            "enabled": false,
            "require_authorization": true
        },
        "python_code": {
            "enabled": true,
            "require_authorization": true
        }
    }
}
```

## Development

### Testing
Walbert includes comprehensive unit tests:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Adding Skills
Skills are Python scripts stored in the datastore:
```python
def my_skill(arg1, arg2):
    # Skill implementation
    return f"Result: {arg1} + {arg2}"
```

### Hardware Integration
Walbert supports hardware interaction through its unified I/O layer:
```python
def handle_hardware_interaction(hardware_action):
    # Hardware interaction logic
    pass
```

## Response Protocol

Walbert uses a block-based response format:
```
~walbert_response_start~
Response text
~walbert_response_end~
~walbert_response_channel_start~
console
~walbert_response_channel_end~
```

## License
MIT License - see LICENSE file for details
