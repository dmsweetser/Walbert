# Walbert - Local-First AI Agent

Walbert is a local-first AI agent system built on llama.cpp compiled binaries.

## Features

- **Local-Only Execution**: Runs entirely on your Linux system using local llama.cpp binaries
- **Multi-Model Support**: Load and manage multiple GGUF models simultaneously
- **SQLite Datastore**: Stores all items, tags, conversations, and memories
- **Hardware Integration**: Interact with USB, serial, and Bluetooth devices
- **Unified Response Protocol**: Consistent block-based format for all responses
- **Configurable I/O Layers**: Enable, disable, or require authorization for different I/O channels

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/walbert.git
cd walbert
```

2. Run the installation script:
```bash
./install.sh
```

3. Configure your system by editing `instance/config.json` and `instance/io_config.json`

## Configuration

### config.json
```json
{
    "model_configs": {
        "ministral": {
            "model_path": "/path/to/ministral-3b.gguf",
            "context_size": 2048,
            "output_tokens": 512,
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05
        },
        "devstral": {
            "model_path": "/path/to/devstral-24b.gguf",
            "context_size": 4096,
            "output_tokens": 1024,
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 50,
            "min_p": 0.1
        }
    },
    "llama_binary_path": "/path/to/llama.cpp/bin/llama-server",
    "log_level": "INFO"
}
```

### io_config.json
```json
{
    "console": {
        "enabled": true,
        "require_authorization": false
    },
    "serial": {
        "enabled": false,
        "require_authorization": true,
        "port": "/dev/ttyUSB0",
        "baudrate": 9600
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
        "enabled": false,
        "require_authorization": true
    }
}
```

## Running Walbert

Start the agent with:
```bash
./run.sh
```

## Testing

Run the test suite with:
```bash
python -m unittest discover tests
```

## License

MIT License - See [LICENSE](LICENSE) for details
