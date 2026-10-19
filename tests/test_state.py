"""Tests for agent state management."""
import pytest
import sys
import os
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.state import AgentState


class MockConfig:
    conversation_log_dir = "instance/conversations"
    database_path = "instance/walbert.db"
    log_level = "DEBUG"
    be_presbyterian = True
    python_execution_enabled = False
    bash_execution_enabled = False
    peer_communication_enabled = False


class TestAgentState:
    """Test the AgentState class."""

    @pytest.fixture
    def state(self, tmp_path):
        """Create an AgentState with a temp directory."""
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        config = MockConfig()
        config.conversation_log_dir = str(conv_dir)
        return AgentState(config)

    def test_init(self, state):
        assert state._self_awareness is not None
        assert state._user_awareness is not None
        assert state._user_directive is not None
        assert state._immediate_task is not None
        assert state._ultimate_task is not None
        assert state._impediment is not None

    def test_system_prompt_generated(self, state):
        prompt = state.system_prompt
        assert "Walbert" in prompt
        assert "machine_details" in prompt or "OS:" in prompt

    def test_refresh_system_prompt(self, state):
        old_prompt = state._system_prompt
        state.refresh_system_prompt()
        assert state._system_prompt is not None
        assert len(state._system_prompt) > 100

    def test_save_load_self_awareness(self, state, tmp_path):
        state._self_awareness = "I am a test agent."
        state._save_self_awareness()
        
        # Load from file
        with open(state._self_awareness_path) as f:
            content = f.read()
        assert "I am a test agent" in content

    def test_save_load_user_awareness(self, state):
        state._user_awareness = "User is a developer."
        state._save_user_awareness()
        
        with open(state._user_awareness_path) as f:
            content = f.read()
        assert "User is a developer" in content

    def test_save_load_user_directive(self, state):
        state._user_directive = "Build a web app."
        state._save_user_directive()
        
        with open(state._user_directive_path) as f:
            content = f.read()
        assert "Build a web app" in content

    def test_save_load_immediate_task(self, state):
        state._immediate_task = "Processing request."
        state._save_immediate_task()
        
        with open(state._immediate_task_path) as f:
            content = f.read()
        assert "Processing request" in content

    def test_save_load_ultimate_task(self, state):
        state._ultimate_task = "Achieve world domination."
        state._save_ultimate_task()
        
        with open(state._ultimate_task_path) as f:
            content = f.read()
        assert "world domination" in content

    def test_save_load_impediment(self, state):
        state._impediment = "No internet access."
        state._save_impediment()
        
        with open(state._impediment_path) as f:
            content = f.read()
        assert "No internet access" in content

    def test_save_load_peer_awareness(self, state):
        state._peer_awareness["192.168.1.100"] = "Peer agent info."
        state._save_peer_awareness()
        
        with open(state._peer_awareness_path) as f:
            content = f.read()
        assert "192.168.1.100" in content

    def test_append_block(self, state):
        state.append_block("test_type", "test content")
        assert len(state._recent_blocks) == 1
        assert state._recent_blocks[0]["type"] == "test_type"
        assert state._recent_blocks[0]["content"] == "test content"

    def test_append_block_limits_history(self, state):
        for i in range(25):
            state.append_block(f"type_{i}", f"content_{i}")
        assert len(state._recent_blocks) <= 20

    def test_set_pending_peer_responses(self, state):
        state.set_pending_peer_responses({"192.168.1.1"})
        assert "192.168.1.1" in state._pending_peer_responses

    def test_get_prompt(self, state):
        prompt = state.get_prompt(user_input="Hello")
        assert "Walbert" in prompt
        assert "Hello" in prompt
        assert "self_awareness" in prompt.lower()

    def test_get_prompt_with_tools(self, state):
        """Test that prompt includes tool definitions when tools are enabled."""
        # Add a tools attribute to state for testing
        class MockTools:
            def to_prompt_format(self):
                return "\n## Available Tools\n[TOOL:filesystem_read]"
        state.tools = MockTools()
        state.tools_enabled = True
        
        prompt = state.get_prompt(user_input="Test", tools_enabled=True, tool_definitions=state.tools.to_prompt_format())
        assert "filesystem_read" in prompt

    def test_get_machine_details(self, state):
        details = state._get_machine_details()
        assert "OS:" in details
        assert "Hostname:" in details

    def test_db_schema_property(self, state):
        """Test db_schema property."""
        # Without db, should return None or empty
        assert state._db_schema is None

    def test_awareness_text_alias(self, state):
        """Test awareness_text property alias."""
        state.awareness_text = "Custom awareness."
        assert state._self_awareness == "Custom awareness."
        
        # Save and verify
        state._save_self_awareness()
        with open(state._self_awareness_path) as f:
            assert "Custom awareness" in f.read()

    def test_update_awareness(self, state):
        """Test update_awareness method."""
        state.update_awareness("Updated awareness.")
        assert state._self_awareness == "Updated awareness."

    def test_sync_state(self, state):
        """Test _sync_state method."""
        # Should not crash
        state._sync_state()

    def test_load_all(self, state):
        """Test _load_all method."""
        # Should not crash
        state._load_all()
