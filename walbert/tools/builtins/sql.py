"""
SQL tool - Execute SQL queries against SQLite databases.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- No security restrictions (wide open per user directive)
"""

import os
import sqlite3
import logging
from typing import Dict, Any

from walbert.tools.base import BaseTool, ToolResult

logger = logging.getLogger("walbert.tools.builtins.sql")


class ExecuteSqlTool(BaseTool):
    name = "db_query"
    description = "Execute a SQL query against a SQLite database."
    parameters = {"db_path": "string?", "sql": "string"}

    def execute(self, params: dict) -> ToolResult:
        sql = params["sql"].strip()

        # Resolve database path
        db_path = params.get("db_path", "instance/walbert.db")

        if not os.path.exists(db_path):
            return ToolResult(False, "", error=f"Database not found: {db_path}")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(sql)

            # For SELECT queries, return results
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result_lines = ["\t".join(columns)]
                for row in rows:
                    result_lines.append("\t".join(str(v) if v is not None else "" for v in row))
                result = "\n".join(result_lines)

                if len(result) > 10000:
                    result = f"{result[:10000]}\n... (truncated, {len(result)} total chars)"

                return ToolResult(
                    True, result,
                    summary=f"Query returned {len(rows)} rows: {len(columns)} columns"
                )
            else:
                conn.commit()
                return ToolResult(
                    True, f"Query executed successfully. Rows affected: {cursor.rowcount}",
                    summary=f"Executed: {sql[:50]}"
                )
        except sqlite3.Error as e:
            return ToolResult(False, "", error=f"Database error: {e}")
        except Exception as e:
            return ToolResult(False, "", error=f"Error executing query: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ===================================================================
# Backward-compatible function wrapper
# ===================================================================

def execute_sql(db_path: str = "instance/walbert.db", sql: str = "", **kwargs) -> str:
    """Legacy wrapper for ExecuteSqlTool."""
    tool = ExecuteSqlTool(kwargs.get("root_dir", ""))
    result = tool.execute({"db_path": db_path, "sql": sql})
    return result.content if result.success else f"Error: {result.error}"
