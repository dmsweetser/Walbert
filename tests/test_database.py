"""
Test cases for DatabaseManager
"""

import unittest
import os
import tempfile
import sqlite3
from walbert.database.manager import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_initialization(self):
        self.assertTrue(os.path.exists(self.db_path))
        self.assertIsNotNone(self.db.conn)
        self.assertIsNotNone(self.db.cursor)

    def test_schema_initialization(self):
        tables = self.db.cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """).fetchall()

        table_names = [table[0] for table in tables]
        self.assertIn("items", table_names)
        self.assertIn("tags", table_names)
        self.assertIn("item_tags", table_names)
        self.assertIn("conversations", table_names)
        self.assertIn("messages", table_names)

    def test_execute_sql(self):
        result = self.db.execute_sql("INSERT INTO items (content, type) VALUES ('test', 'text')")
        self.assertIn("SQL executed successfully", result)

        result = self.db.execute_sql("SELECT * FROM items")
        self.assertIn("test", result)

    def test_start_conversation(self):
        conv_id = self.db.start_conversation("console")
        self.assertEqual(conv_id, 1)

        result = self.db.execute_sql("SELECT * FROM conversations")
        self.assertIn("console", result)

    def test_add_message(self):
        conv_id = self.db.start_conversation("console")
        msg_id = self.db.add_message(conv_id, "test message", "user")

        result = self.db.execute_sql(f"SELECT * FROM messages WHERE id = {msg_id}")
        self.assertIn("test message", result)

    def test_end_conversation(self):
        conv_id = self.db.start_conversation("console")
        self.db.end_conversation(conv_id, "test summary")

        result = self.db.execute_sql(f"SELECT * FROM conversations WHERE id = {conv_id}")
        self.assertIn("test summary", result)

    def test_get_schema(self):
        schema = self.db.get_schema()
        self.assertIn("Table: items", schema)
        self.assertIn("Table: tags", schema)
        self.assertIn("Table: conversations", schema)
        self.assertIn("Table: messages", schema)

if __name__ == "__main__":
    unittest.main()
