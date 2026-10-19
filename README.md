# Walbert - Local AI Agent

Walbert is a local-first AI agent designed to run entirely on your machine. It supports autonomous operation, peer-to-peer communication, code execution, and a **pluggable tool system** for extending capabilities.

## Features

- **Local-First**: Runs entirely on your machine, no cloud dependencies
- **Autonomous Operation**: Can operate without user input
- **Peer Communication**: Communicate with other Walbert agents on the network
- **Code Execution**: Execute Python and Bash code safely
- **Database Integration**: Full SQLite database access
- **Tool Calling**: 25+ built-in tools for filesystem, web, email, Google, and more
- **Custom Tools**: Create and persist your own tools — fully auditable
- **Modular Architecture**: Easily extensible design

## Tool System

Walbert uses a block-based tool format for agent actions:

```
[TOOL:tool_name]
param1:value1
param2:
multi-line value here
[TOOL_END]
```

### Built-in Tools (25+)

| Category | Tools |
|----------|-------|
| **Filesystem** | `filesystem_read`, `filesystem_write`, `filesystem_list`, `filesystem_search`, `filesystem_delete`, `filesystem_copy` |
| **Web** | `web_get`, `web_post`, `web_browser` |
| **Email** | `email_list`, `email_read`, `email_send`, `email_search` |
| **Google** | `google_search`, `google_gmail_read`, `google_gmail_send`, `google_calendar_list`, `google_calendar_create`, `google_drive_list`, `google_drive_upload` |
| **System** | `shell_run`, `shell_script`, `create_tool`, `list_tools`, `get_tool` |

### Creating Custom Tools

Walbert can create persistent tools at runtime using the `create_tool` tool:

```
[TOOL:create_tool]
tool_name:my_weather_tool
description:Get weather for a city
parameters_json:{"city": {"type": "string", "description": "City name", "required": true}}
handler_code:    import requests
    url = f"https://wttr.in/{kwargs.get('city', 'London')}?format=j1"
    data = requests.get(url).json()
    return data['current_condition'][0]['lang_en'][0]['value']
[TOOL_END]
```

Custom tools are:
- Saved to `walbert/instance_tools/{tool_name}.py` (for import)
- Copied to `instance/tools/{tool_name}.py` (for auditing)
- Registered in `instance/tools/registry.json`

You can audit any tool's source code in `instance/tools/` at any time.

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
├── walbert/agent.py              # Main agent loop, tool execution
│   ├── walbert/state.py          # State, system prompt, awareness
│   ├── walbert/parser.py         # Legacy block parser
│   ├── walbert/executor.py       # Legacy block executor
│   ├── walbert/comms.py          # Peer communication
│   │
│   ├── walbert/tools/            # NEW: Tool system
│   │   ├── registry.py           # Tool registry (persisted JSON)
│   │   ├── parser.py             # [TOOL:name] block parser
│   │   ├── executor.py           # Tool dispatch
│   │   └── builtins/             # Built-in tool implementations
│   │       ├── filesystem.py     # File read/write/list/search
│   │       ├── web.py            # HTTP GET/POST, browser
│   │       ├── email.py          # IMAP/SMTP email
│   │       ├── google.py         # Google API (OAuth)
│   │       └── shell.py          # Shell + tool management
│   │
│   ├── walbert/database/         # SQLite manager
│   └── walbert/models/           # Model manager
│
├── walbert/instance_tools/       # User-created tools (auto-generated)
│
└── instance/
    ├── config.json               # Configuration
    ├── tools/
    │   └── registry.json         # Tool registry (auditable)
    │   └── {tool_name}.py        # Custom tool source (auditable)
    └── conversations/
```

## License

MIT