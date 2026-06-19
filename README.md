# Walbert - Local-First AI Agent
      
```
 ___            ___     
/   \          /   \     
\_   \        /  __/     
 _\   \      /  /__     
 \___  \____/   __/     
     \_       _/     
       | @ @  \_     
       |     
     _/     /\     
    /o)  (o/\ \_     
    \_____/ /     
      \____/     
             
```

Welcome to Walbert! The local-first AI agent.

## Features

- **Local-First Execution**: Runs on your Linux system using local llama.cpp binaries
- **Single Model Focus**: Optimized for Devstral-24B-Instruct-GGUF for high-quality reasoning
- **SQLite Datastore**: Walbert has **FULL AUTONOMY** over its database schema and persistence
- **Unified Response Protocol**: Walbert must emit **all responses and internal deliberations** using the following block-based format with `walbert_` prefix:
    - `[walbert_console_response]` - Direct console output to the user
    - `[walbert_sql_execute]` - SQL commands for database operations
    - `[walbert_python_execute]` - Python code execution blocks
- **Full Database Autonomy**: Walbert manages **ALL** aspects of its database:
  - Schema design and evolution
  - Data storage and retrieval
  - Memory and knowledge persistence
- **Skill Preservation System**: Breaks down complex tasks into reusable components
- **Raw Conversation Logging**: Full prompts and responses logged to conversation files
- **Zero Hard-Coded Persistence**: All database operations handled through the protocol
- **Python Execution**: Execute Python code in the main application's virtual environment
- **Autonomous Operation**: Continues working even without user input
- **Error Resilience**: Provides errors as feedback without disrupting execution
- **Package Management**: Install Python packages directly in the main environment using the `pip_install` command

## Installation

1. Clone the repository:
```bash
git clone https://github.com/dmsweetser/walbert.git
cd walbert
```

2. Run the installation script:
```bash
./install.sh
```

3. Configure your system by editing `instance/config.json`

## Configuration

### config.json
```json
{
    "model_configs": {
        "model": {
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
    "mmproj_path": "",
    "log_level": "INFO",
    "server_port": 8080,
    "server_health_check_timeout": 2,
    "server_startup_timeout": 60,
    "python_execution_timeout": 30,
    "autonomous_operation_timeout": 120,
    "conversation_log_dir": "instance/conversations",
    "database_path": "instance/walbert.db"
}
```

## Running Walbert

Start the agent with:
```bash
./run.sh
```

Available commands:
- `exit`/`quit`: Exit the program
- `inet on`: Enable internet access for Python execution
- `inet off`: Disable internet access for Python execution
- `pip_install <package>`: Install a Python package in the main environment
- Any other input will be treated as a request to Walbert

## Testing (there are no tests)

Run the test suite with:
```bash
python -m unittest discover tests
```

## License

MIT License - See [LICENSE](LICENSE) for details
