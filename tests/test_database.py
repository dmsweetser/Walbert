#!/usr/bin/env python3
"""
Unit tests for database operations
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_schema()

    def test_store_and_retrieve_item(self):
        item_id = self.db.store_item("test content", ["tag1", "tag2"], "text")
        self.assertIsInstance(item_id, int)

        items = self.db.retrieve_items_by_tag("tag1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "test content")

    def test_retrieve_by_multiple_tags(self):
        self.db.store_item("content1", ["tag1", "tag2"], "text")
        self.db.store_item("content2", ["tag1"], "text")
        self.db.store_item("content3", ["tag2", "tag3"], "text")

        items = self.db.retrieve_items_by_multiple_tags(["tag1", "tag2"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "content1")

    def test_conversation_operations(self):
        conv_id = self.db.start_conversation("console")
        self.assertIsInstance(conv_id, int)

        msg_id = self.db.add_message(conv_id, "test message", "user")
        self.assertIsInstance(msg_id, int)

        self.db.end_conversation(conv_id, "test summary")

    def test_skill_storage(self):
        skill_id = self.db.store_item(
            "def test_skill(): return 'test'",
            ["skill", "test", "example"],
            "skill"
        )
        self.assertIsInstance(skill_id, int)

        skills = self.db.retrieve_items_by_multiple_tags(["skill", "test"])
        self.assertEqual(len(skills), 1)

if __name__ == '__main__':
    unittest.main()
