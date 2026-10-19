"""Tests for the legacy block executor."""
import pytest
import sys
import os
import tempfile
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.executor import BlockExecutor


class MockConfig:
    python_execution_enabled = True
    bash_execution_enabled = True
    python_execution_timeout = 10
    bash_execution_timeout = 10


class MockDB:
    def execute_sql(self, sql):
        return "OK"
    def get_schema(self):
        return "TABLE items"


class TestBlockExecutor:
    """Test the legacy BlockExecutor."""

    @pytest.fixture
    def executor(self):
        return BlockExecutor(MockConfig(), MockDB())

    def test_execute_sql(self, executor):
        result = executor.execute({"type": "sql_execute", "content": "SELECT * FROM items"})
        assert result is not None
        assert "sql_result" in result["type"]

    def test_execute_python_disabled(self, executor):
        executor.config.python_execution_enabled = False
        result = executor.execute({"type": "python_execute", "content": "print('hello')"})
        assert "disabled" in result["content"].lower()

    def test_execute_bash_disabled(self, executor):
        executor.config.bash_execution_enabled = False
        result = executor.execute({"type": "bash_execute", "content": "echo hello"})
        assert "disabled" in result["content"].lower()

    def test_execute_python_enabled(self, executor):
        result = executor.execute({"type": "python_execute", "content": "print('hello test')"})
        assert result is not None
        assert "python_result" in result["type"]
        assert "hello test" in result["content"]

    def test_execute_bash_enabled(self, executor):
        result = executor.execute({"type": "bash_execute", "content": "echo 'hello test'"})
        assert result is not None
        assert "bash_result" in result["type"]
        assert "hello test" in result["content"]

    def test_execute_console_blocking(self, executor):
        result = executor.execute({
            "type": "console_response_blocking",
            "content": "Important message"
        })
        assert result is not None
        assert "Important message" in result["content"]

    def test_execute_console_nonblocking(self, executor):
        result = executor.execute({
            "type": "console_response_nonblocking",
            "content": "Info message"
        })
        assert result is not None
        assert "Info message" in result["content"]

    def test_execute_unknown_type(self, executor):
        result = executor.execute({"type": "unknown_type", "content": "test"})
        assert result is None
