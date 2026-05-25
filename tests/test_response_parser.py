#!/usr/bin/env python3
"""
Unit tests for response parsing
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walbert.response.parser import ResponseParser

class TestResponseParser(unittest.TestCase):
    def setUp(self):
        self.parser = ResponseParser()

    def test_parse_simple_response(self):
        response = """
        ~walbert_response_start~
        This is a test response
        ~walbert_response_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("response"), "This is a test response")

    def test_parse_channel(self):
        response = """
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("channel"), "console")

    def test_parse_decision_blocks(self):
        response = """
        ~walbert_should_query_datastore_start~
        YES
        ~walbert_should_query_datastore_end~
        ~walbert_conversation_complete_start~
        NO
        ~walbert_conversation_complete_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("should_query_datastore"), "YES")
        self.assertEqual(parsed.get("conversation_complete"), "NO")

    def test_parse_sql_execute_block(self):
        response = """
        ~walbert_sql_execute_start~
        SELECT * FROM items WHERE type = 'text'
        ~walbert_sql_execute_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("sql_execute"), "SELECT * FROM items WHERE type = 'text'")

    def test_parse_skill_execution_block(self):
        # Skill execution is now handled through SQL queries
        pass

    def test_parse_hardware_action_block(self):
        response = """
        ~walbert_hardware_action_start~
        {"peripheral_type": "serial", "action": "connect", "data": {"port": "/dev/ttyUSB0"}}
        ~walbert_hardware_action_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("hardware_action", {}).get("peripheral_type"), "serial")
        self.assertEqual(parsed.get("hardware_action", {}).get("action"), "connect")

    def test_parse_complex_response(self):
        response = """
        ~walbert_should_query_datastore_start~
        YES
        ~walbert_should_query_datastore_end~
        ~walbert_sql_execute_start~
        SELECT * FROM items WHERE type='skill'
        ~walbert_sql_execute_end~
        ~walbert_response_start~
        I found 3 skills in the database.
        ~walbert_response_end~
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        ~walbert_conversation_complete_start~
        NO
        ~walbert_conversation_complete_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("should_query_datastore"), "YES")
        self.assertEqual(parsed.get("sql_execute"), "SELECT * FROM items WHERE type='skill'")
        self.assertEqual(parsed.get("response"), "I found 3 skills in the database.")
        self.assertEqual(parsed.get("channel"), "console")
        self.assertEqual(parsed.get("conversation_complete"), "NO")

if __name__ == '__main__':
    unittest.main()
