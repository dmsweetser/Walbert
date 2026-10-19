"""Shared test fixtures and mocks for Walbert tests."""
import sys
import os
import json
import tempfile
import shutil
from unittest.mock import MagicMock, Mock, patch
from pathlib import Path

import pytest

# Ensure Walbert is importable
WALBERT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WALBERT_ROOT))


@pytest.fixture
def temp_walbert_dir(tmp_path):
    """Create a temporary Walbert-like directory structure."""
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    (instance_dir / "conversations").mkdir()
    (instance_dir / "tools").mkdir()
    (instance_dir / "tools" / "registry.json").write_text(json.dumps({"custom_tools": {}}))
    
    walbert_dir = tmp_path / "walbert"
    walbert_dir.mkdir()
    (walbert_dir / "__init__.py").write_text("")
    
    return tmp_path


@pytest.fixture
def mock_config():
    """Create a mock config object."""
    config = MagicMock()
    config.model_configs = {
        'model': MagicMock(
            model_path="/dev/null/model.gguf",
            context_size=4096,
            output_tokens=1024,
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            min_p=0.05
        )
    }
    config.llama_binary_path = "/dev/null/llama-completion"
    config.mmproj_path = ""
    config.log_level = "DEBUG"
    config.server_port = 8080
    config.server_health_check_timeout = 2
    config.server_startup_timeout = 60
    config.python_execution_timeout = 30
    config.autonomous_operation_timeout = 120
    config.conversation_log_dir = "instance/conversations"
    config.walbert_port = 8081
    config.udp_port = 9999
    config.be_presbyterian = True
    config.peer_communication_enabled = False
    config.python_execution_enabled = False
    config.bash_execution_enabled = False
    config.database_path = "instance/walbert.db"
    config.bluetooth_device = None
    config.user_input_timeout = 60
    return config


@pytest.fixture
def mock_db():
    """Create a mock database manager."""
    db = MagicMock()
    db.execute_sql.return_value = "OK"
    db.get_schema.return_value = "TABLE items\n  COLUMN id INTEGER\n  COLUMN content TEXT\n  COLUMN created_at TIMESTAMP"
    db.connect = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def mock_model_manager():
    """Create a mock model manager."""
    mm = MagicMock()
    mm.execute_model.return_value = "[walbert_console_response_nonblocking_start]\nTest response\n[walbert_console_response_nonblocking_end]"
    mm.validate_binaries = MagicMock()
    mm.shutdown = MagicMock()
    return mm


@pytest.fixture
def mock_llm_response():
    """Generate a mock LLM response with various block types."""
    return """Here is my response:

[walbert_console_response_nonblocking_start]
I have processed your request and taken the following actions.
[walbert_console_response_nonblocking_end]

[walbert_self_awareness_start]
I am Walbert, a local AI agent with full hardware access and autonomy.
[walbert_self_awareness_end]
"""


@pytest.fixture
def mock_tool_response():
    """Generate a mock LLM response with tool calls."""
    return """Let me help with that:

[TOOL:filesystem_read]
path:/etc/hostname
[TOOL_END]

[TOOL:shell_run]
command:echo "Hello"
timeout:5
[TOOL_END]

[walbert_console_response_nonblocking_start]
Done with the operations.
[walbert_console_response_nonblocking_end]
"""


@pytest.fixture
def mock_peer_config():
    """Create a mock config with peer communication enabled."""
    config = mock_config()
    config.peer_communication_enabled = True
    config.walbert_port = 8081
    return config


@pytest.fixture
def mock_network_manager():
    """Create a mock network manager."""
    nm = MagicMock()
    nm.get_peer_list.return_value = []
    nm.start = MagicMock()
    nm.stop = MagicMock()
    nm.send_to_peer = MagicMock(return_value='{"status": "ok"}')
    nm.get_pending_messages = MagicMock(return_value=[])
    return nm
