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

    def test_parse_decision_block(self):
        response = """
        ~walbert_should_call_smarter_cousin_start~
        YES
        ~walbert_should_call_smarter_cousin_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("should_call_smarter_cousin"), "YES")

    def test_parse_action_block(self):
        response = """
        ~walbert_db_command_start~
        RETRIEVE_ITEMS
        {"tags": ["test"]}
        ~walbert_db_command_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("db_command", {}).get("command"), "RETRIEVE_ITEMS")
        self.assertEqual(parsed.get("db_command", {}).get("args", {}).get("tags"), ["test"])

    def test_parse_complex_response(self):
        response = """
        ~walbert_should_query_datastore_start~
        YES
        ~walbert_should_query_datastore_end~
        ~walbert_db_command_start~
        RETRIEVE_ITEMS
        {"tags": ["example"]}
        ~walbert_db_command_end~
        ~walbert_response_start~
        Here is the retrieved data.
        ~walbert_response_end~
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        """
        parsed = self.parser.parse_response(response)
        self.assertEqual(parsed.get("should_query_datastore"), "YES")
        self.assertEqual(parsed.get("db_command", {}).get("command"), "RETRIEVE_ITEMS")
        self.assertEqual(parsed.get("response"), "Here is the retrieved data.")
        self.assertEqual(parsed.get("channel"), "console")

if __name__ == '__main__':
    unittest.main()
