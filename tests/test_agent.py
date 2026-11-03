"""Tests for the Walbert agent with mocked LLM responses (TOOLS ONLY version)."""
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
        agent.tool_executor = MagicMock()
        agent.tool_executor.execute = MagicMock(return_value={
            "success": True,
            "result": "Executed",
            "content": "Executed"
        })
        return agent

    def test_init(self, mock_config):
        agent = WalbertAgent(mock_config)
        assert agent.config == mock_config
        assert agent.state is not None
        assert agent.tool_parser is not None
        assert agent.tools is not None
        assert agent.tools_enabled is True

    def test_start_conversation(self, agent, mock_config):
        agent.start_conversation()
        assert agent.model_ready is True
        assert agent.session_dir is not None

    def test_end_conversation(self, agent, mock_config):
        agent.start_conversation()
        agent.end_conversation()
        assert agent.session_dir is None

    def test_generate_response_with_tool_calls(self, agent, mock_tool_response):
        """Test that agent processes tool calls from LLM."""
        agent.model_manager.execute_model.return_value = mock_tool_response
        agent.start_conversation()

        # Replace the real executor with a mock (start_conversation creates a real one)
        agent.tool_executor = MagicMock()
        agent.tool_executor.execute = MagicMock(return_value={
            "success": True,
            "result": "Executed",
            "content": "Executed"
        })

        output = []
        original_write = agent.write_output
        def capture_write(text, block_type=None):
            output.append((text, block_type))
        agent.write_output = capture_write

        result = agent._generate_response("Read /etc/hostname", None)

        # Should have processed tool blocks and called write_output
        assert len(output) > 0, f"No output captured. State blocks: {agent.state._recent_blocks}"

    def test_execute_tool_blocks(self, agent):
        """Test tool block execution."""
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

    def test_generate_autonomous(self, agent, mock_llm_response):
        """Test autonomous mode generation."""
        agent.model_manager.execute_model.return_value = mock_llm_response
        agent.start_conversation()

        result = agent._generate_autonomous("last input", None)
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

    def test_generate_response_no_tools(self, agent, mock_llm_response):
        """Test response generation with tools disabled."""
        agent.tools_enabled = False
        agent.model_manager.execute_model.return_value = mock_llm_response
        agent.start_conversation()

        output = []
        def capture_write(text, block_type=None):
            output.append((text, block_type))
        agent.write_output = capture_write

        result = agent._generate_response("Hello", None)
        # Should still return model response, just no tool execution
        assert result == mock_llm_response

    def test_log_full_prompt_and_response(self, agent):
        """Test that prompt and response are logged."""
        agent.start_conversation()
        agent._log_full_prompt_and_response("test prompt", "test response")
        assert os.path.exists(agent.session_dir)
        files = os.listdir(agent.session_dir)
        assert any('prompt' in f for f in files)
        assert any('response' in f for f in files)

    def test_execute_tool_blocks_error(self, agent):
        """Test tool execution with failure result."""
        from walbert.tools.registry import ToolRegistry
        from walbert.tools.executor import ToolExecutor
        agent.tools = ToolRegistry()
        agent.tool_executor = ToolExecutor(agent.tools)
        agent.tool_executor.execute = MagicMock(return_value={
            "success": False,
            "result": "",
            "error": "Command failed"
        })

        tool_calls = [{"name": "shell_run", "params": {"command": "false"}}]
        agent._execute_tool_blocks(tool_calls)

        # Should have logged error blocks
        assert len(agent.state._recent_blocks) > 0
        # Check that error was recorded
        error_blocks = [b for b in agent.state._recent_blocks if 'error' in str(b).lower()]
        assert len(error_blocks) > 0

    def test_conversation_flow(self, agent, mock_tool_response):
        """Test a full conversation flow."""
        agent.model_manager.execute_model.return_value = mock_tool_response
        agent.start_conversation()

        # Simulate user input
        input_queue = queue.Queue()
        input_queue.put(("user_input", "Hello"))

        output = []
        def capture_write(text, block_type=None):
            output.append((text, block_type))
        agent.write_output = capture_write

        # Generate response
        result = agent._generate_response("Hello", None)
        assert result == mock_tool_response

        # Agent should be waiting for user
        assert agent.waiting_for_user is True

        # End conversation
        agent.end_conversation()
        assert agent.session_dir is None
