"""
Test cases for ResponseParser
"""

import unittest
from walbert.response.parser import ResponseParser

class TestResponseParser(unittest.TestCase):
    def setUp(self):
        self.parser = ResponseParser()

    def test_parse_response(self):
        response_text = """
        ~walbert_response_start~
        test response
        ~walbert_response_end~
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        ~walbert_should_query_datastore_start~
        YES
        ~walbert_should_query_datastore_end~
        ~walbert_conversation_complete_start~
        NO
        ~walbert_conversation_complete_end~
        ~walbert_sql_execute_start~
        SELECT * FROM items
        ~walbert_sql_execute_end~
        ~walbert_skill_execute_start~
        test_skill
        ~walbert_skill_execute_end~
        """

        parsed = self.parser.parse_response(response_text)

        self.assertEqual(parsed["response"], "test response")
        self.assertEqual(parsed["channel"], "console")
        self.assertEqual(parsed["should_query_datastore"], "YES")
        self.assertEqual(parsed["conversation_complete"], "NO")
        self.assertEqual(parsed["sql_execute"], "SELECT * FROM items")
        self.assertEqual(parsed["skill_execute"], "test_skill")

    def test_parse_partial_response(self):
        response_text = """
        ~walbert_response_start~
        test response
        ~walbert_response_end~
        ~walbert_response_channel_start~
        console
        ~walbert_response_channel_end~
        """

        parsed = self.parser.parse_response(response_text)

        self.assertEqual(parsed["response"], "test response")
        self.assertEqual(parsed["channel"], "console")
        self.assertNotIn("should_query_datastore", parsed)
        self.assertNotIn("conversation_complete", parsed)

    def test_parse_empty_response(self):
        parsed = self.parser.parse_response("")
        self.assertEqual(parsed, {})

if __name__ == "__main__":
    unittest.main()
