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
        ~walbert_should_execute_skill_start~
        NO
        ~walbert_should_execute_skill_end~
        ~walbert_should_call_smarter_cousin_start~
        YES
        ~walbert_should_call_smarter_cousin_end~
        ~walbert_conversation_complete_start~
        NO
        ~walbert_conversation_complete_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("should_query_datastore"), "YES")
        self.assertEqual(parsed.get("should_execute_skill"), "NO")
        self.assertEqual(parsed.get("should_call_smarter_cousin"), "YES")
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
        response = """
        ~walbert_skill_execution_start~
        test_skill
        {"args": ["arg1", "arg2"]}
        ~walbert_skill_execution_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("skill_execution", {}).get("command"), "test_skill")
        self.assertEqual(parsed.get("skill_execution", {}).get("args", {}).get("args"), ["arg1", "arg2"])

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
        SELECT * FROM items WHERE tags LIKE '%example%'
        ~walbert_sql_execute_end~
        ~walbert_should_execute_skill_start~
        NO
        ~walbert_should_execute_skill_end~
        ~walbert_should_call_smarter_cousin_start~
        NO
        ~walbert_should_call_smarter_cousin_end~
        ~walbert_response_start~
        I found 3 items related to your query.
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
        self.assertEqual(parsed.get("sql_execute"), "SELECT * FROM items WHERE tags LIKE '%example%'")
        self.assertEqual(parsed.get("should_execute_skill"), "NO")
        self.assertEqual(parsed.get("should_call_smarter_cousin"), "NO")
        self.assertEqual(parsed.get("response"), "I found 3 items related to your query.")
        self.assertEqual(parsed.get("channel"), "console")
        self.assertEqual(parsed.get("conversation_complete"), "NO")

if __name__ == '__main__':
    unittest.main()
