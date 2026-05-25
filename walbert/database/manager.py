"""
Database manager implementation
"""

import sqlite3
import logging
from typing import List, Tuple

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
                content TEXT,
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
                content TEXT,
                sender TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        self.conn.commit()
        self.logger.debug("Database schema initialized")

    def get_schema(self) -> str:
        """Get current database schema"""
        self.logger.debug("Retrieving database schema")
        schema = {}

        tables = self.cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """).fetchall()

        for table in tables:
            table_name = table[0]
            schema[table_name] = {}

            columns = self.cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
            schema[table_name]['columns'] = [
                {
                    'name': col[1],
                    'type': col[2],
                    'not_null': bool(col[3]),
                    'default_value': col[4],
                    'primary_key': bool(col[5])
                } for col in columns
            ]

            fks = self.cursor.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
            schema[table_name]['foreign_keys'] = [
                {
                    'id': fk[0],
                    'seq': fk[1],
                    'table': fk[2],
                    'from': fk[3],
                    'to': fk[4],
                    'on_update': fk[5],
                    'on_delete': fk[6],
                    'match': fk[7]
                } for fk in fks
            ]

        schema_str = "Current Database Schema:\n\n"
        for table_name, table_info in schema.items():
            schema_str += f"Table: {table_name}\n"
            schema_str += "Columns:\n"
            for col in table_info['columns']:
                schema_str += f"  - {col['name']} ({col['type']})"
                if col['primary_key']:
                    schema_str += " PRIMARY KEY"
                if col['not_null']:
                    schema_str += " NOT NULL"
                if col['default_value'] is not None:
                    schema_str += f" DEFAULT {col['default_value']}"
                schema_str += "\n"

            if table_info['foreign_keys']:
                schema_str += "Foreign Keys:\n"
                for fk in table_info['foreign_keys']:
                    schema_str += f"  - {fk['from']} REFERENCES {fk['table']}({fk['to']})"
                    if fk['on_delete'] != 'NO ACTION':
                        schema_str += f" ON DELETE {fk['on_delete']}"
                    if fk['on_update'] != 'NO ACTION':
                        schema_str += f" ON UPDATE {fk['on_update']}"
                    schema_str += "\n"

            schema_str += "\n"

        return schema_str

    def execute_sql(self, sql: str) -> str:
        """Execute arbitrary SQL statement"""
        self.logger.debug(f"Executing SQL: {sql}")
        try:
            result = self.cursor.execute(sql)

            if sql.strip().upper().startswith("SELECT"):
                rows = result.fetchall()
                if not rows:
                    return "Query executed successfully. No rows returned."

                output = "Query results:\n"
                columns = [desc[0] for desc in result.description]
                output += "\t".join(columns) + "\n"
                output += "-" * (sum(len(col) for col in columns) + len(columns) * 3) + "\n"

                for row in rows:
                    output += "\t".join(str(val) for val in row) + "\n"

                return output
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

    def add_message(self, conversation_id: int, content: str, sender: str = "user") -> int:
        """Add a message to a conversation"""
        self.logger.debug(f"Adding message to conversation {conversation_id} from {sender}")
        self.cursor.execute(
            "INSERT INTO messages (conversation_id, content, sender) VALUES (?, ?, ?)",
            (conversation_id, content, sender)
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

    def close(self):
        """Close database connection"""
        self.logger.debug("Closing database connection")
        self.conn.close()
