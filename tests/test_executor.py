"""Tests for the tool executor."""
import pytest
import sys
import os
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.tools.registry import ToolRegistry
from walbert.tools.executor import ToolExecutor


class TestToolExecutor:
    """Test the tool executor."""

    @pytest.fixture
    def executor(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        return ToolExecutor(reg)

    def test_execute_known_tool(self, executor, tmp_path):
        # Create a test file first
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("Hello from test file")
        result = executor.execute("filesystem_read", {"path": str(test_file)})
        assert result["success"] is True
        assert "Hello from test file" in result["result"]

    def test_execute_unknown_tool(self, executor):
        result = executor.execute("nonexistent_tool", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_execute_shell_run(self, executor):
        result = executor.execute("shell_run", {
            "command": "echo 'hello from test'",
            "timeout": "5"
        })
        assert result["success"] is True
        assert "hello from test" in result["result"]

    def test_execute_shell_script_python(self, executor):
        result = executor.execute("shell_script", {
            "script": "print('hello from python script')",
            "language": "python",
            "timeout": "10"
        })
        assert result["success"] is True
        assert "hello from python script" in result["result"]

    def test_execute_shell_script_bash(self, executor):
        result = executor.execute("shell_script", {
            "script": "echo 'hello from bash script'",
            "language": "bash",
            "timeout": "10"
        })
        assert result["success"] is True
        assert "hello from bash script" in result["result"]

    def test_execute_filesystem_write_and_read(self, executor, tmp_path):
        test_file = str(tmp_path / "test_output.txt")
        # Write
        result = executor.execute("filesystem_write", {
            "path": test_file,
            "content": "Hello, World!"
        })
        assert result["success"] is True
        # Read
        result = executor.execute("filesystem_read", {"path": test_file})
        assert result["success"] is True
        assert "Hello, World!" in result["result"]

    def test_execute_filesystem_list(self, executor):
        result = executor.execute("filesystem_list", {
            "path": "/tmp",
            "recursive": "false"
        })
        assert result["success"] is True
        assert "# Contents of" in result["result"]

    def test_execute_list_tools(self, executor):
        result = executor.execute("list_tools", {})
        assert result["success"] is True
        assert "Available Tools" in result["result"]

    def test_execute_get_tool(self, executor):
        result = executor.execute("get_tool", {"tool_name": "filesystem_read"})
        assert result["success"] is True
        assert "filesystem_read" in result["result"]

    def test_execute_web_get_fallback(self, executor):
        """Test web_get with curl fallback (no requests needed)."""
        result = executor.execute("web_get", {
            "url": "https://httpbin.org/get",
            "timeout": "10"
        })
        # Should succeed with curl fallback
        assert result["success"] is True

    def test_execute_create_tool(self, executor):
        """Test creating a custom tool."""
        result = executor.execute("create_tool", {
            "tool_name": "test_echo",
            "description": "Echoes input",
            "parameters_json": '{"text": {"type": "string", "description": "Text to echo", "required": true}}',
            "handler_code": "    return f'Echo: {kwargs.get(\"text\", \"\")}'"
        })
        assert result["success"] is True
        assert "created successfully" in result["result"]

    def test_execute_custom_tool_after_creation(self, executor, tmp_path):
        """Test using a just-created custom tool."""
        # The create_tool handler uses the default registry path,
        # so we need to use the same registry for both creation and execution.
        from walbert.tools.registry import ToolRegistry
        import os
        from pathlib import Path
        
        walbert_root = Path(__file__).parent.parent
        reg_path = str(walbert_root / "instance" / "tools" / "registry.json")
        
        # Create a fresh executor with the default registry
        fresh_executor = ToolExecutor(ToolRegistry(reg_path))
        
        # Create the tool
        result = fresh_executor.execute("create_tool", {
            "tool_name": "test_math",
            "description": "Adds two numbers",
            "parameters_json": '{"a": {"type": "number", "required": true}, "b": {"type": "number", "required": true}}',
            "handler_code": "    a = float(kwargs.get('a', 0))\n    b = float(kwargs.get('b', 0))\n    return str(a + b)"
        })
        assert result["success"] is True
        
        # Use the tool - create a fresh executor with the updated registry
        fresh_executor2 = ToolExecutor(ToolRegistry(reg_path))
        result = fresh_executor2.execute("test_math", {"a": "5", "b": "3"})
        assert result["success"] is True
        assert "8" in result["result"]

    def test_execute_web_post(self, executor):
        """Test web_post with curl fallback."""
        result = executor.execute("web_post", {
            "url": "https://httpbin.org/post",
            "body": '{"test": "data"}',
            "headers": '{"Content-Type": "application/json"}'
        })
        # Should succeed with curl fallback
        assert result["success"] is True

    def test_execute_filesystem_search(self, executor):
        """Test filesystem_search."""
        result = executor.execute("filesystem_search", {
            "path": "/tmp",
            "pattern": "*.py"
        })
        assert result["success"] is True
        # Should show results or "No files matching"

    def test_execute_db_query(self, executor, tmp_path):
        """Test db_query tool."""
        import sqlite3
        # Create a test database
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES ('walbert')")
        conn.commit()
        conn.close()
        
        result = executor.execute("db_query", {
            "db_path": db_path,
            "sql": "SELECT * FROM test"
        })
        assert result["success"] is True
        assert "walbert" in result["result"]
        assert "id" in result["result"]

    def test_execute_db_query_insert(self, executor, tmp_path):
        """Test db_query with INSERT."""
        import sqlite3
        db_path = str(tmp_path / "test2.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()
        
        result = executor.execute("db_query", {
            "db_path": db_path,
            "sql": "INSERT INTO items (value) VALUES ('test')"
        })
        assert result["success"] is True
        assert "1 row" in result["result"]

    def test_execute_python_execute(self, executor):
        """Test python_execute tool."""
        result = executor.execute("python_execute", {
            "code": "print('hello from python tool')",
            "timeout": "10"
        })
        assert result["success"] is True
        assert "hello from python tool" in result["result"]

    def test_execute_python_execute_empty(self, executor):
        """Test python_execute with empty code."""
        result = executor.execute("python_execute", {
            "code": "",
            "timeout": "10"
        })
        assert result["success"] is True
        assert "No Python code provided" in result["result"]

    def test_execute_peer_send_no_comms(self, executor):
        """Test peer_send when comms is not configured."""
        result = executor.execute("peer_send", {
            "peer_ip": "192.168.1.1",
            "message": "hello"
        })
        assert result["success"] is True
        assert "not enabled" in result["result"]
