"""
Database manager implementation
"""

import sqlite3
import logging
import base64
import json
from typing import List, Tuple, Any, Dict

class DatabaseManager:
    """Manages SQLite database operations"""
    def __init__(self, db_path: str = "instance/walbert.db"):
        self.db_path = db_path
        self.logger = logging.getLogger('walbert')
        self.connect()

    def connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.cursor = self.conn.cursor()
        self.init_schema()
        self.logger = logging.getLogger('walbert.database')
        self.logger.debug(f"Connected to database at {self.db_path}")

    def init_schema(self):
        """Initialize database schema"""
        self.logger.debug("Initializing database schema")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                content_b64 TEXT,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_tags (
                item_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id),
                PRIMARY KEY (item_id, tag_id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                summary TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                channel TEXT
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER,
                content_b64 TEXT,
                sender TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        # Create indexes for better performance
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_channel ON conversations(channel)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender)")

        self.conn.commit()
        self.logger.debug("Database schema initialized")

    def get_schema(self) -> str:
        """Get current database schema"""
        self.logger.debug("Retrieving database schema")

        tables = self.cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """).fetchall()

        schema_str = "Current Database Schema:\n\n"
        for table in tables:
            table_name = table[0]
            schema_str += f"Table: {table_name}\n"

            columns = self.cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
            schema_str += "Columns:\n"
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                schema_str += f"  - {col_name} ({col_type})"

                if col[5]:  # primary key
                    schema_str += " PRIMARY KEY"
                if col[3]:  # not null
                    schema_str += " NOT NULL"
                if col[4] is not None:  # default value
                    schema_str += f" DEFAULT {col[4]}"
                schema_str += "\n"

            fks = self.cursor.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
            if fks:
                schema_str += "Foreign Keys:\n"
                for fk in fks:
                    schema_str += f"  - {fk[3]} REFERENCES {fk[2]}({fk[4]})"
                    if fk[6] != 'NO ACTION':
                        schema_str += f" ON DELETE {fk[6]}"
                    if fk[5] != 'NO ACTION':
                        schema_str += f" ON UPDATE {fk[5]}"
                    schema_str += "\n"

            schema_str += "\n"

        return schema_str

    def _encode_content(self, content: Any) -> str:
        """Encode content to base64"""
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content)
        else:
            content_str = str(content)
        return base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    def _decode_content(self, content_b64: str) -> Any:
        """Decode content from base64"""
        content_str = base64.b64decode(content_b64.encode('utf-8')).decode('utf-8')
        try:
            return json.loads(content_str)
        except json.JSONDecodeError:
            return content_str

    def execute_sql(self, sql: str) -> str:
        """Execute arbitrary SQL statement"""
        self.logger.debug(f"Executing SQL: {sql}")
        try:
            result = self.cursor.execute(sql)

            if sql.strip().upper().startswith("SELECT"):
                rows = result.fetchall()
                if not rows:
                    return "Query executed successfully. No rows returned."

                output = []
                columns = [desc[0] for desc in result.description]
                output.append("\t".join(columns))
                output.append("-" * (sum(len(col) for col in columns) + len(columns) * 3))

                for row in rows:
                    decoded_row = []
                    for val in row:
                        if isinstance(val, str) and ('content_b64' in columns or columns[row.index(val)] == 'content_b64'):
                            decoded_val = self._decode_content(val)
                            decoded_row.append(str(decoded_val))
                        else:
                            decoded_row.append(str(val) if val is not None else "NULL")
                    output.append("\t".join(decoded_row))

                return "\n".join(output)
            else:
                self.conn.commit()
                return f"SQL executed successfully. Rows affected: {self.cursor.rowcount}"
        except Exception as e:
            self.logger.error(f"SQL execution error: {e}")
            return f"Error executing SQL: {e}"

    def start_conversation(self, channel: str) -> int:
        """Start a new conversation"""
        self.logger.debug(f"Starting new conversation on channel {channel}")
        self.cursor.execute(
            "INSERT INTO conversations (channel) VALUES (?)",
            (channel,)
        )
        conv_id = self.cursor.lastrowid
        self.conn.commit()
        self.logger.debug(f"Started conversation with ID {conv_id}")
        return conv_id

    def add_message(self, conversation_id: int, content: Any, sender: str = "user") -> int:
        """Add a message to a conversation"""
        self.logger.debug(f"Adding message to conversation {conversation_id} from {sender}")
        content_b64 = self._encode_content(content)
        self.cursor.execute(
            "INSERT INTO messages (conversation_id, content_b64, sender) VALUES (?, ?, ?)",
            (conversation_id, content_b64, sender)
        )
        msg_id = self.cursor.lastrowid
        self.logger.debug(f"Added message with ID {msg_id}")
        return msg_id

    def end_conversation(self, conversation_id: int, summary: str):
        """End a conversation"""
        self.logger.debug(f"Ending conversation {conversation_id} with summary: {summary}")
        self.cursor.execute(
            "UPDATE conversations SET end_time = CURRENT_TIMESTAMP, summary = ? WHERE id = ?",
            (summary, conversation_id)
        )
        self.conn.commit()
        self.logger.debug(f"Conversation {conversation_id} ended")

    def add_item(self, content: Any, item_type: str) -> int:
        """Add an item to the database"""
        self.logger.debug(f"Adding item of type {item_type}")
        content_b64 = self._encode_content(content)
        self.cursor.execute(
            "INSERT INTO items (content_b64, type) VALUES (?, ?)",
            (content_b64, item_type)
        )
        item_id = self.cursor.lastrowid
        self.conn.commit()
        self.logger.debug(f"Added item with ID {item_id}")
        return item_id

    def get_item(self, item_id: int) -> Any:
        """Get an item from the database"""
        self.logger.debug(f"Retrieving item with ID {item_id}")
        result = self.cursor.execute(
            "SELECT content_b64 FROM items WHERE id = ?",
            (item_id,)
        ).fetchone()
        if result:
            return self._decode_content(result[0])
        return None

    def close(self):
        """Close database connection"""
        self.logger.debug("Closing database connection")
        self.conn.close()
