"""
Database manager implementation
"""

import sqlite3
import logging
from typing import List, Tuple

logger = logging.getLogger('walbert')

class DatabaseManager:
    """Manages SQLite database operations"""
    def __init__(self, db_path: str = "instance/walbert.db"):
        self.db_path = db_path
        self.connect()

    def connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.init_schema()

    def init_schema(self):
        """Initialize database schema"""
        # Items table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                content TEXT,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tags table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        """)

        # Item-tags mapping
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_tags (
                item_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id),
                PRIMARY KEY (item_id, tag_id)
            )
        """)

        # Conversations table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                summary TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                channel TEXT
            )
        """)

        # Messages table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER,
                content TEXT,
                sender TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        self.conn.commit()

    def store_item(self, content: str, tags: List[str], item_type: str = "text") -> int:
        """Store an item with tags"""
        self.cursor.execute(
            "INSERT INTO items (content, type) VALUES (?, ?)",
            (content, item_type)
        )
        item_id = self.cursor.lastrowid

        for tag in tags:
            # Add tag if it doesn't exist
            self.cursor.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                (tag,)
            )
            # Link item to tag
            self.cursor.execute("""
                INSERT INTO item_tags (item_id, tag_id)
                VALUES (?, (SELECT id FROM tags WHERE name = ?))
            """, (item_id, tag))

        self.conn.commit()
        return item_id

    def retrieve_items_by_tag(self, tag: str) -> List[Tuple]:
        """Retrieve items by tag"""
        self.cursor.execute("""
            SELECT i.id, i.content, i.type, i.created_at
            FROM items i
            JOIN item_tags it ON i.id = it.item_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
        """, (tag,))
        return self.cursor.fetchall()

    def retrieve_items_by_multiple_tags(self, tags: List[str]) -> List[Tuple]:
        """Retrieve items by multiple tags (AND logic)"""
        placeholders = ','.join(['?'] * len(tags))
        self.cursor.execute(f"""
            SELECT i.id, i.content, i.type, i.created_at
            FROM items i
            JOIN item_tags it ON i.id = it.item_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name IN ({placeholders})
            GROUP BY i.id
            HAVING COUNT(DISTINCT t.name) = {len(tags)}
        """, tags)
        return self.cursor.fetchall()

    def start_conversation(self, channel: str) -> int:
        """Start a new conversation"""
        self.cursor.execute(
            "INSERT INTO conversations (channel) VALUES (?)",
            (channel,)
        )
        return self.cursor.lastrowid

    def add_message(self, conversation_id: int, content: str, sender: str = "user") -> int:
        """Add a message to a conversation"""
        self.cursor.execute(
            "INSERT INTO messages (conversation_id, content, sender) VALUES (?, ?, ?)",
            (conversation_id, content, sender)
        )
        return self.cursor.lastrowid

    def end_conversation(self, conversation_id: int, summary: str):
        """End a conversation"""
        self.cursor.execute(
            "UPDATE conversations SET end_time = CURRENT_TIMESTAMP, summary = ? WHERE id = ?",
            (summary, conversation_id)
        )
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()
