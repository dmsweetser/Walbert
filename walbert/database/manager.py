import sqlite3
import threading
import logging
from typing import Dict, Any

class DatabaseManager:
    """Minimal SQLite manager that executes SQL verbatim."""
    def __init__(self, db_path: str = "instance/walbert.db"):
        self.db_path = db_path
        self.logger = logging.getLogger("walbert.database")
        self.conn = None
        self.cursor = None
        self._lock = threading.Lock()

    def connect(self):
        """Connect to SQLite database."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.logger.debug(f"Connected to database at {self.db_path}")

    def init_schema(self):
        """Optional: create a minimal default table."""
        with self._lock:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.commit()

    def get_schema(self) -> str:
        """Return raw schema information without formatting."""
        with self._lock:
            tables = self.cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """).fetchall()

            output = []
            for (table_name,) in tables:
                output.append(f"TABLE {table_name}")
                cols = self.cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
                for col in cols:
                    output.append(f"  COLUMN {col[1]} {col[2]}")
            return "\n".join(output)

    def execute_sql(self, sql: str) -> Any:
        """Execute SQL exactly as provided — no splitting, no formatting."""
        with self._lock:
            try:
                self.logger.debug(f"Executing SQL verbatim:\n{sql}")

                result = self.cursor.execute(sql)

                # SELECT → return raw rows
                if sql.strip().upper().startswith("SELECT"):
                    rows = result.fetchall()
                    return rows

                # Non-SELECT → commit and return success
                self.conn.commit()
                return "OK"

            except Exception as e:
                self.logger.error(f"SQL execution error: {e}")
                return f"ERROR: {e}"

    def close(self):
        with self._lock:
            self.logger.debug("Closing database connection")
            self.conn.close()
