# Walbert - Local-First AI Agent

Walbert is a local-first AI agent system built on llama.cpp compiled binaries.

## Features

- **Local-Only Execution**: Runs entirely on your Linux system using local llama.cpp binaries
- **Multi-Model Support**: Load and manage multiple GGUF models simultaneously
- **SQLite Datastore**: Stores all data with full autonomy for Walbert
- **Hardware Integration**: Interact with serial devices
- **Unified Response Protocol**: Consistent block-based format for all responses
- **Configurable I/O Layers**: Enable or disable different I/O channels
- **Full Database Autonomy**: Walbert manages its own schema and data persistence
- **Raw Conversation Logging**: All input/output and raw LLM output logged to files

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
        "devstral": {
            "model_path": "/path/to/devstral-24b.gguf",
            "context_size": 2048,
            "output_tokens": 512,
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05
        }
    },
    "llama_binary_path": "/path/to/llama.cpp/bin/llama-server",
    "log_level": "INFO"
}
```

### io_config.json
```json
{
    "user_interactive_channel": "console",
    "console": {
        "enabled": true
    },
    "serial": {
        "enabled": false,
        "port": "/dev/ttyUSB0",
        "baudrate": 9600
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
