# Walbert - Local-First AI Agent

Walbert is a local-first AI agent system built on llama.cpp compiled binaries.

## Features

- **Local-First Execution**: Runs on your Linux system using local llama.cpp binaries
- **Single Model Focus**: Optimized for Devstral-24B-Instruct-GGUF for high-quality reasoning
- **SQLite Datastore**: Walbert has **FULL AUTONOMY** over its database schema and persistence
- **Unified Response Protocol**: Walbert must emit **all responses and internal deliberations** using the following block-based format with `walbert_` prefix:
    - `[walbert_console_response]` - Direct console output to the user
    - `[walbert_sql_execute]` - SQL commands for database operations
    - `[walbert_python_requirements]` - Python package requirements
    - `[walbert_python_execute]` - Python code execution blocks
    - `[walbert_sql_result]` - SQL query results
    - `[walbert_python_result]` - Python execution results
    - `[walbert_error]` - Error reporting
- **Full Database Autonomy**: Walbert manages **ALL** aspects of its database:
  - Schema design and evolution
  - Data storage and retrieval
  - Memory and knowledge persistence
- **Skill Preservation System**: Breaks down complex tasks into reusable components
- **Raw Conversation Logging**: All input/output and raw LLM output logged to files
- **Zero Hard-Coded Persistence**: All database operations handled through the protocol
- **Python Execution**: Execute Python code in sandboxed environment with package requirements
- **Autonomous Operation**: Continues working even without user input
- **Error Resilience**: Provides errors as feedback without disrupting execution
- **Theological Alignment**: Philosophically and morally aligned with the Presbyterian Church of America

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
    "log_level": "INFO"
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
