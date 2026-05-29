"""
Database manager implementation
"""

import sqlite3
import logging
from typing import List, Tuple, Any, Dict

class DatabaseManager:
    """Manages SQLite database operations with FULL AUTONOMY for Walbert"""
    def __init__(self, db_path: str = "instance/walbert.db"):
        self.db_path = db_path
        self.logger = logging.getLogger('walbert.database')
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
        """Initialize database schema with minimal structure"""
        self.logger.debug("Initializing database schema")

        # Create minimal items table - Walbert will define all other tables
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        self.logger.debug("Database schema initialized with minimal items table only")

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
                    output_row = []
                    for val in row:
                        output_row.append(str(val) if val is not None else "NULL")
                    output.append("\t".join(output_row))

                return "\n".join(output)
            else:
                self.conn.commit()
                return f"SQL executed successfully. Rows affected: {self.cursor.rowcount}"
        except Exception as e:
            self.logger.error(f"SQL execution error: {e}")
            return f"Error executing SQL: {e}"

    def close(self):
        """Close database connection"""
        self.logger.debug("Closing database connection")
        self.conn.close()
