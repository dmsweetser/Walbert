"""Tests for the block parser (legacy walbert_* blocks)."""
import pytest
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from walbert.parser import BlockParser


class TestBlockParser:
    """Test the legacy block parser."""

    def test_parse_console_response(self):
        parser = BlockParser()
        text = "[walbert_console_response_nonblocking_start]\nHello world\n[walbert_console_response_nonblocking_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "console_response_nonblocking"
        assert "Hello world" in blocks[0]["content"]

    def test_parse_multiple_blocks(self):
        parser = BlockParser()
        text = """[walbert_console_response_nonblocking_start]
First response
[walbert_console_response_nonblocking_end]

[walbert_self_awareness_start]
I am Walbert.
[walbert_self_awareness_end]"""
        blocks = parser.parse(text)
        assert len(blocks) == 2
        assert blocks[0]["type"] == "console_response_nonblocking"
        assert blocks[1]["type"] == "self_awareness"
        assert "I am Walbert" in blocks[1]["content"]

    def test_parse_sql_block(self):
        parser = BlockParser()
        text = "[walbert_sql_execute_start]\nSELECT * FROM items;[walbert_sql_execute_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "sql_execute"
        assert "SELECT * FROM items" in blocks[0]["content"]

    def test_parse_python_block(self):
        parser = BlockParser()
        text = "[walbert_python_execute_start]\nprint('hello')\n[walbert_python_execute_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "python_execute"
        assert "print('hello')" in blocks[0]["content"]

    def test_parse_bash_block(self):
        parser = BlockParser()
        text = "[walbert_bash_execute_start]\nls -la\n[walbert_bash_execute_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "bash_execute"
        assert "ls -la" in blocks[0]["content"]

    def test_parse_awareness_blocks(self):
        parser = BlockParser()
        text = """[walbert_self_awareness_start]
I am an agent.
[walbert_self_awareness_end]
[walbert_user_awareness_start]
I know the user.
[walbert_user_awareness_end]
[walbert_immediate_task_start]
Do something.
[walbert_immediate_task_end]
[walbert_ultimate_task_start]
Achieve goals.
[walbert_ultimate_task_end]
[walbert_impediment_start]
No blockers.
[walbert_impediment_end]
[walbert_user_directive_start]
Follow user instructions.
[walbert_user_directive_end]"""
        blocks = parser.parse(text)
        assert len(blocks) == 6
        types = [b["type"] for b in blocks]
        assert "self_awareness" in types
        assert "user_awareness" in types
        assert "immediate_task" in types
        assert "ultimate_task" in types
        assert "impediment" in types
        assert "user_directive" in types

    def test_parse_with_backticks(self):
        parser = BlockParser()
        text = """```
[walbert_console_response_nonblocking_start]
Hello
[walbert_console_response_nonblocking_end]
```"""
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert "Hello" in blocks[0]["content"]

    def test_parse_no_blocks(self):
        parser = BlockParser()
        text = "Just plain text with no blocks"
        blocks = parser.parse(text)
        assert len(blocks) == 0

    def test_parse_unclosed_block(self):
        parser = BlockParser()
        text = "[walbert_console_response_nonblocking_start]\nUnclosed content"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "console_response_nonblocking"
        assert "Unclosed content" in blocks[0]["content"]

    def test_parse_peer_message_block(self):
        parser = BlockParser()
        text = "[walbert_peer_192_168_1_100_message_send_start]\nHello peer\n[walbert_peer_192_168_1_100_message_send_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert "peer_192_168_1_100_message_send" in blocks[0]["type"]

    def test_parse_peer_awareness_block(self):
        parser = BlockParser()
        text = "[walbert_peer_192_168_1_100_awareness_start]\nPeer info\n[walbert_peer_192_168_1_100_awareness_end]"
        blocks = parser.parse(text)
        assert len(blocks) == 1
        assert "peer_192_168_1_100_awareness" in blocks[0]["type"]
