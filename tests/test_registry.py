"""Tests for the tool registry."""
import pytest
import sys
import json
import os
import tempfile
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.tools.registry import ToolRegistry, DEFAULT_TOOLS


class TestToolRegistry:
    """Test the tool registry."""

    def test_load_default_tools(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        tools = reg.list_tools()
        assert len(tools) >= 25  # At least the default tools
        assert "filesystem_read" in tools
        assert "shell_run" in tools
        assert "list_tools" in tools

    def test_tool_has_required_fields(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        for name, tool in reg.list_tools().items():
            assert "name" in tool, f"Tool {name} missing 'name'"
            assert "description" in tool, f"Tool {name} missing 'description'"
            assert "handler" in tool, f"Tool {name} missing 'handler'"
            assert "parameters" in tool, f"Tool {name} missing 'parameters'"

    def test_get_specific_tool(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        tool = reg.get_tool("filesystem_read")
        assert tool is not None
        assert tool["name"] == "filesystem_read"
        assert "path" in tool["parameters"]

    def test_get_unknown_tool(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        tool = reg.get_tool("nonexistent_tool")
        assert tool is None

    def test_to_prompt_format(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        prompt = reg.to_prompt_format()
        assert "Available Tools" in prompt
        assert "filesystem_read" in prompt
        assert "shell_run" in prompt
        assert "web_get" in prompt

    def test_register_custom_tool(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        
        tool_def = {
            "name": "test_custom",
            "description": "A test custom tool",
            "parameters": {"x": {"type": "string", "description": "Input", "required": True}},
            "category": "custom",
            "handler": "test.module.handler"
        }
        result = reg.register_tool(tool_def)
        assert result is True
        
        tool = reg.get_tool("test_custom")
        assert tool is not None
        assert tool["description"] == "A test custom tool"

    def test_unregister_custom_tool(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        
        # Register first
        tool_def = {
            "name": "test_unregister",
            "description": "To be unregistered",
            "parameters": {},
            "category": "custom",
            "handler": "test.handler"
        }
        reg.register_tool(tool_def)
        assert reg.get_tool("test_unregister") is not None
        
        # Now unregister
        result = reg.unregister_tool("test_unregister")
        assert result is True
        assert reg.get_tool("test_unregister") is None

    def test_cannot_unregister_builtin(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        result = reg.unregister_tool("filesystem_read")
        assert result is False

    def test_persist_to_disk(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        
        tool_def = {
            "name": "test_persist",
            "description": "Test persistence",
            "parameters": {},
            "category": "custom",
            "handler": "test.handler"
        }
        reg.register_tool(tool_def)
        
        # Read the file directly
        with open(reg_path) as f:
            data = json.load(f)
        
        assert "custom_tools" in data
        assert "test_persist" in data["custom_tools"]

    def test_reload_from_disk(self, tmp_path):
        reg_path = str(tmp_path / "registry.json")
        
        # Create registry and add a tool
        reg1 = ToolRegistry(reg_path)
        tool_def = {
            "name": "test_reload",
            "description": "Test reload",
            "parameters": {},
            "category": "custom",
            "handler": "test.handler"
        }
        reg1.register_tool(tool_def)
        
        # Create new registry (should reload from disk)
        reg2 = ToolRegistry(reg_path)
        tool = reg2.get_tool("test_reload")
        assert tool is not None
        assert tool["description"] == "Test reload"

    def test_builtin_tools_count(self, tmp_path):
        """Verify we have the expected number of default tools."""
        reg_path = str(tmp_path / "registry.json")
        reg = ToolRegistry(reg_path)
        tools = reg.list_tools()
        
        # Should have at least the built-in tools
        expected_tools = [
            "filesystem_read", "filesystem_write", "filesystem_list",
            "filesystem_search", "shell_run", "shell_script",
            "web_get", "web_post", "web_browser",
            "email_list", "email_read", "email_send", "email_search",
            "google_search", "google_gmail_read", "google_gmail_send",
            "google_calendar_list", "google_calendar_create",
            "google_drive_list", "google_drive_upload",
            "create_tool", "list_tools", "get_tool",
        ]
        for tool_name in expected_tools:
            assert tool_name in tools, f"Missing expected tool: {tool_name}"
