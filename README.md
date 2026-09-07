# Walbert - Local AI Agent

Walbert is a local-first AI agent designed to run entirely on your machine. It supports autonomous operation, peer-to-peer communication, and execution of Python/Bash code.

## Features

- **Local-First**: Runs entirely on your machine, no cloud dependencies
- **Autonomous Operation**: Can operate without user input
- **Peer Communication**: Communicate with other Walbert agents on the network
- **Code Execution**: Execute Python and Bash code safely
- **Audio Support**: Voice input/output with Bluetooth audio support
- **Database Integration**: Full SQLite database access
- **Modular Architecture**: Easily extensible design

## Installation

### Linux

```bash
./_install.sh
```

### Windows

```cmd
install.bat
```

## Usage

```bash
./_run.sh
```

## Configuration

Edit `instance/config.json` to configure:
- Model paths
- Audio settings
- Execution permissions
- Network settings

## Architecture

```
main.py
│
├── walbert/agent.py
│   ├── walbert/state.py
│   ├── walbert/parser.py
│   ├── walbert/executor.py
│   ├── walbert/models/manager.py
│   ├── walbert/database/manager.py
│   ├── walbert/comms.py
│   └── walbert/audio_thread.py
└── instance/
    ├── config.json
    └── conversations/
```

## License

MIT