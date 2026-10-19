"""
SQL execution tool - database query execution via SQLite.
"""

import os
import sqlite3
import logging

logger = logging.getLogger("walbert.tools.builtins.sql")


def execute_sql(db_path: str = "instance/walbert.db", sql: str = "", **kwargs) -> str:
    """Execute a SQL statement against a SQLite database.
    
    Args:
        db_path: Path to the SQLite database file.
        sql: SQL statement to execute (SELECT, INSERT, UPDATE, DELETE, etc.).
    """
    if not sql or not sql.strip():
        return "Error: No SQL statement provided."
    
    # Resolve relative paths
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.getcwd(), db_path)
    
    if not os.path.exists(db_path):
        return f"Error: Database not found: {db_path}"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = sql.strip()
        is_select = query.upper().startswith("SELECT")
        
        cursor.execute(query)
        
        if is_select:
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            if not rows:
                conn.close()
                return "Query returned no rows."
            
            # Format as tabular text
            result_lines = ["| " + " | ".join(columns) + " |"]
            result_lines.append("|" + "|".join(["---"] * len(columns)) + "|")
            for row in rows:
                result_lines.append("| " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |")
            
            conn.close()
            return f"# Query result ({len(rows)} row(s))\n" + "\n".join(result_lines)
        else:
            conn.commit()
            rowcount = cursor.rowcount
            conn.close()
            return f"OK — {rowcount} row(s) affected."
    
    except sqlite3.Error as e:
        return f"SQLite error: {e}"
    except Exception as e:
        return f"SQL execution error: {e}"
