"""Tests for the tool parser ([TOOL:name] blocks)."""
import pytest
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.tools.parser import ToolParser


class TestToolParser:
    """Test the tool format parser."""

    def test_parse_single_tool(self):
        parser = ToolParser()
        text = "[TOOL:filesystem_read]\npath:/etc/hosts\n[TOOL_END]"
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "filesystem_read"
        assert tools[0]["params"]["path"] == "/etc/hosts"

    def test_parse_multiple_tools(self):
        parser = ToolParser()
        text = """Some intro text.

[TOOL:filesystem_read]
path:/etc/hostname
[TOOL_END]

Middle text.

[TOOL:shell_run]
command:echo hello
timeout:5
[TOOL_END]

Outro text."""
        tools = parser.parse(text)
        assert len(tools) == 2
        assert tools[0]["name"] == "filesystem_read"
        assert tools[0]["params"]["path"] == "/etc/hostname"
        assert tools[1]["name"] == "shell_run"
        assert tools[1]["params"]["command"] == "echo hello"
        assert tools[1]["params"]["timeout"] == "5"

    def test_parse_multiline_param(self):
        parser = ToolParser()
        text = """[TOOL:filesystem_write]
path:
/tmp/test.txt
content:
Line 1 of content.
Line 2 of content.
Line 3 of content.
[TOOL_END]"""
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "filesystem_write"
        assert tools[0]["params"]["path"] == "/tmp/test.txt"
        assert "Line 1" in tools[0]["params"]["content"]
        assert "Line 2" in tools[0]["params"]["content"]
        assert "Line 3" in tools[0]["params"]["content"]

    def test_parse_empty_param(self):
        parser = ToolParser()
        text = "[TOOL:shell_run]\ncommand:\n[TOOL_END]"
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["params"]["command"] == ""

    def test_parse_json_param(self):
        parser = ToolParser()
        text = """[TOOL:create_tool]
tool_name:test_tool
description:A test tool
parameters_json:{"name": {"type": "string", "required": true}}
handler_code:def run(**kwargs):\n    return "hello"
[TOOL_END]"""
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "create_tool"
        assert '"name"' in tools[0]["params"]["parameters_json"]

    def test_parse_no_tools(self):
        parser = ToolParser()
        text = "Just plain text with no tool blocks"
        tools = parser.parse(text)
        assert len(tools) == 0

    def test_parse_unclosed_tool(self):
        parser = ToolParser()
        text = "[TOOL:filesystem_read]\npath:/etc/hosts"
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "filesystem_read"
        assert tools[0]["params"]["path"] == "/etc/hosts"

    def test_parse_tool_with_blank_lines(self):
        parser = ToolParser()
        text = """[TOOL:shell_run]

command:echo test

timeout:5

[TOOL_END]"""
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["params"]["command"] == "echo test"
        assert tools[0]["params"]["timeout"] == "5"

    def test_parse_case_insensitive(self):
        parser = ToolParser()
        text = "[tool:filesystem_read]\npath:/etc/hosts\n[tool_end]"
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "filesystem_read"

    def test_parse_bracket_style(self):
        """Test compact bracket-style tools (no newlines between tags)."""
        parser = ToolParser()
        # This format is not supported - the parser expects newlines between params
        text = "[TOOL:filesystem_read]\npath:/etc/hosts\n[TOOL_END]"
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "filesystem_read"
        assert tools[0]["params"]["path"] == "/etc/hosts"

    def test_parse_web_get(self):
        parser = ToolParser()
        text = """[TOOL:web_get]
url:https://example.com
timeout:30
[TOOL_END]"""
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "web_get"
        assert tools[0]["params"]["url"] == "https://example.com"
        assert tools[0]["params"]["timeout"] == "30"

    def test_parse_email_send(self):
        parser = ToolParser()
        text = """[TOOL:email_send]
to:user@example.com
subject:Test
body:Hello World
[TOOL_END]"""
        tools = parser.parse(text)
        assert len(tools) == 1
        assert tools[0]["name"] == "email_send"
        assert tools[0]["params"]["to"] == "user@example.com"
        assert tools[0]["params"]["subject"] == "Test"
        assert tools[0]["params"]["body"] == "Hello World"
