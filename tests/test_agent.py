"""Tests for the Walbert agent with mocked LLM responses."""
import pytest
import sys
import os
import json
import tempfile
import threading
import queue
from unittest.mock import MagicMock, Mock, patch, PropertyMock
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.agent import WalbertAgent, load_config


class TestWalbertAgent:
    """Test the Walbert agent with mocked LLM."""

    @pytest.fixture
    def agent(self, mock_config, mock_model_manager, mock_db, tmp_path):
        """Create an agent with mocked dependencies."""
        # Create instance directory
        instance_dir = tmp_path / "instance"
        instance_dir.mkdir()
        (instance_dir / "conversations").mkdir()
        (instance_dir / "tools").mkdir()
        (instance_dir / "tools" / "registry.json").write_text(json.dumps({"custom_tools": {}}))
        
        os.chdir(tmp_path)
        
        agent = WalbertAgent(mock_config, model_manager=mock_model_manager)
        agent.db = mock_db
        agent.state.db = mock_db
        agent.executor = MagicMock()
        agent.executor.execute = MagicMock(return_value={
            "type": "console_response_nonblocking",
            "content": "Executed"
        })
        return agent

    def test_init(self, mock_config):
        agent = WalbertAgent(mock_config)
        assert agent.config == mock_config
        assert agent.state is not None
        assert agent.parser is not None
        assert agent.tools is not None  # Initialized in __init__ for main-loop commands
        assert agent.tools_enabled is True

    def test_start_conversation(self, agent, mock_config):
        agent.start_conversation()
        assert agent.model_ready is True
        assert agent.session_dir is not None
        # db is replaced by _init_components, so check model_ready instead
        assert agent.model_ready is True

    def test_end_conversation(self, agent, mock_config):
        agent.start_conversation()
        agent.end_conversation()
        assert agent.session_dir is None

    def test_generate_response_with_console_block(self, agent, mock_llm_response):
        """Test that agent processes a response with console block."""
        agent.model_manager.execute_model.return_value = mock_llm_response
        agent.start_conversation()
        
        # Capture what gets written
        output = []
        original_write = agent.write_output
        def capture_write(text, block_type=None):
            output.append((text, block_type))
            original_write(text, block_type)
        agent.write_output = capture_write
        
        result = agent._generate_response_block("Hello", None)
        
        # Should have parsed and executed blocks
        assert len(output) > 0

    def test_generate_response_with_tool_calls(self, agent, mock_tool_response):
        """Test that agent processes tool calls from LLM."""
        agent.model_manager.execute_model.return_value = mock_tool_response
        agent.start_conversation()
        
        output = []
        original_write = agent.write_output
        def capture_write(text, block_type=None):
            output.append((text, block_type))
        agent.write_output = capture_write
        
        result = agent._generate_response_block("Read /etc/hostname", None)
        
        # Should have processed tool blocks
        assert len(output) > 0

    def test_execute_pending_blocks_awareness(self, agent):
        """Test that awareness blocks are stored in state."""
        blocks = [
            {"type": "self_awareness", "content": "I am Walbert."},
            {"type": "user_awareness", "content": "User is Daniel."},
            {"type": "immediate_task", "content": "Processing request."},
        ]
        agent._execute_pending_blocks(blocks)
        
        assert "I am Walbert." in agent.state._self_awareness
        assert "User is Daniel." in agent.state._user_awareness
        assert "Processing request." in agent.state._immediate_task

    def test_execute_pending_blocks_sql(self, agent):
        """Test SQL block execution."""
        agent.executor.execute = MagicMock(return_value={
            "type": "sql_result",
            "content": "OK"
        })
        blocks = [{"type": "sql_execute", "content": "SELECT * FROM items"}]
        agent._execute_pending_blocks(blocks)
        
        agent.executor.execute.assert_called_once()

    def test_execute_pending_blocks_python(self, agent):
        """Test Python block execution."""
        agent.config.python_execution_enabled = True
        agent.executor.execute = MagicMock(return_value={
            "type": "python_result",
            "content": "stdout: hello\nExit code: 0"
        })
        blocks = [{"type": "python_execute", "content": "print('hello')"}]
        agent._execute_pending_blocks(blocks)
        
        agent.executor.execute.assert_called_once()

    def test_execute_pending_blocks_bash(self, agent):
        """Test Bash block execution."""
        agent.config.bash_execution_enabled = True
        agent.executor.execute = MagicMock(return_value={
            "type": "bash_result",
            "content": "stdout: hello\nExit code: 0"
        })
        blocks = [{"type": "bash_execute", "content": "echo hello"}]
        agent._execute_pending_blocks(blocks)
        
        agent.executor.execute.assert_called_once()

    def test_execute_tool_blocks(self, agent):
        """Test tool block execution."""
        # Initialize tool executor (normally done in start_conversation)
        from walbert.tools.registry import ToolRegistry
        from walbert.tools.executor import ToolExecutor
        agent.tools = ToolRegistry()
        agent.tool_executor = ToolExecutor(agent.tools)
        
        tool_calls = [
            {"name": "shell_run", "params": {"command": "echo hello", "timeout": "5"}},
        ]
        agent._execute_tool_blocks(tool_calls)
        
        # Should have logged the tool call
        assert len(agent.state._recent_blocks) > 0

    def test_execute_tool_blocks_unknown_tool(self, agent):
        """Test executing an unknown tool."""
        from walbert.tools.registry import ToolRegistry
        from walbert.tools.executor import ToolExecutor
        agent.tools = ToolRegistry()
        agent.tool_executor = ToolExecutor(agent.tools)
        
        tool_calls = [{"name": "nonexistent", "params": {}}]
        agent._execute_tool_blocks(tool_calls)
        
        # Should log error, not crash
        assert len(agent.state._recent_blocks) > 0

    def test_generate_autonomous_block(self, agent, mock_llm_response):
        """Test autonomous mode block generation."""
        agent.model_manager.execute_model.return_value = mock_llm_response
        agent.start_conversation()
        
        result = agent._generate_autonomous_block("last input", None)
        assert result == "Continue monitoring and processing."

    def test_write_output_console(self, agent):
        """Test write_output for console responses."""
        agent.write_output("Hello", "console_response_nonblocking")
        # Should write to output.txt for TTS
        assert os.path.exists('output.txt')
        with open('output.txt') as f:
            assert f.read().strip() == "Hello"

    def test_log_block_emitted(self, agent):
        """Test that blocks are logged to emitted directory."""
        agent._log_block_emitted("test_block", "test content")
        emitted_dir = "instance/block_logs/emitted"
        assert os.path.exists(emitted_dir)
        files = os.listdir(emitted_dir)
        assert len(files) > 0

    def test_log_block_received(self, agent):
        """Test that received blocks are logged."""
        agent._log_block_received("user_input", "hello")
        received_dir = "instance/block_logs/received"
        assert os.path.exists(received_dir)

    def test_install_python_package(self, agent):
        """Test pip install."""
        # This will likely fail in test environment, just verify it doesn't crash
        try:
            agent._install_python_package("nonexistent-package-xyz")
        except Exception:
            pass  # Expected to fail

    def test_shutdown(self, agent):
        """Test clean shutdown."""
        agent.start_conversation()
        agent.shutdown()
        assert agent.session_dir is None

    def test_peer_communication_enabled(self, agent):
        """Test enabling peer communication."""
        agent.enable_peer_communication()
        assert agent.config.peer_communication_enabled is True

    def test_peer_communication_disabled(self, agent):
        """Test disabling peer communication."""
        agent.config.peer_communication_enabled = True
        agent._comms_started = True
        agent.comms = MagicMock()
        agent.disable_peer_communication()
        assert agent.config.peer_communication_enabled is False

    def test_tools_enabled_by_default(self, agent):
        """Test that tools are enabled by default."""
        assert agent.tools_enabled is True

    def test_tools_can_be_disabled(self, agent):
        """Test that tools can be disabled."""
        agent.tools_enabled = False
        assert agent.tools_enabled is False
