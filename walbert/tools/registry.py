"""
Tool Registry - Manages the collection of available tools.
Tools are persisted to a JSON file so the user can audit them at any time.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("walbert.tools.registry")

DEFAULT_TOOLS = {
    "filesystem_read": {
        "name": "filesystem_read",
        "description": "Read the contents of a file. Returns the full text content.",
        "parameters": {
            "path": {"type": "string", "description": "Absolute or relative file path to read", "required": True}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.read_file"
    },
    "filesystem_write": {
        "name": "filesystem_write",
        "description": "Write content to a file. Creates parent directories if needed. Overwrites existing content.",
        "parameters": {
            "path": {"type": "string", "description": "File path to write to", "required": True},
            "content": {"type": "string", "description": "Content to write", "required": True}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.write_file"
    },
    "filesystem_list": {
        "name": "filesystem_list",
        "description": "List files and directories in a directory. Returns names with types and sizes.",
        "parameters": {
            "path": {"type": "string", "description": "Directory path to list", "required": True},
            "recursive": {"type": "boolean", "description": "List recursively", "required": False, "default": False}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.list_directory"
    },
    "filesystem_search": {
        "name": "filesystem_search",
        "description": "Search for files matching a glob pattern in a directory tree.",
        "parameters": {
            "path": {"type": "string", "description": "Root directory to search in", "required": True},
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py', '*.txt')", "required": True}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.search_files"
    },
    "filesystem_delete": {
        "name": "filesystem_delete",
        "description": "Delete a file or empty directory. Use with caution.",
        "parameters": {
            "path": {"type": "string", "description": "File or directory path to delete", "required": True}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.delete_path"
    },
    "filesystem_copy": {
        "name": "filesystem_copy",
        "description": "Copy a file from source to destination. Creates parent dirs for destination.",
        "parameters": {
            "src": {"type": "string", "description": "Source file path", "required": True},
            "dst": {"type": "string", "description": "Destination file path", "required": True}
        },
        "category": "filesystem",
        "handler": "walbert.tools.builtins.filesystem.copy_file"
    },
    "web_get": {
        "name": "web_get",
        "description": "Fetch a URL and return its HTML/text content. Good for reading web pages, APIs, documentation.",
        "parameters": {
            "url": {"type": "string", "description": "Full URL to fetch (http:// or https://)", "required": True},
            "timeout": {"type": "integer", "description": "Request timeout in seconds", "required": False, "default": 30}
        },
        "category": "web",
        "handler": "walbert.tools.builtins.web.http_get"
    },
    "web_post": {
        "name": "web_post",
        "description": "Send a POST request to a URL with optional JSON body. Returns response text and status code.",
        "parameters": {
            "url": {"type": "string", "description": "URL to POST to", "required": True},
            "body": {"type": "string", "description": "JSON body to send", "required": False, "default": ""},
            "headers": {"type": "string", "description": "JSON headers dict (e.g. '{\"Content-Type\": \"application/json\"}')", "required": False, "default": ""}
        },
        "category": "web",
        "handler": "walbert.tools.builtins.web.http_post"
    },
    "web_browser": {
        "name": "web_browser",
        "description": "Navigate to a URL and extract page content as text. Handles JavaScript-rendered pages. Use for browsing websites.",
        "parameters": {
            "url": {"type": "string", "description": "URL to navigate to", "required": True},
            "wait_seconds": {"type": "integer", "description": "Seconds to wait for page to load", "required": False, "default": 2}
        },
        "category": "web",
        "handler": "walbert.tools.builtins.web.browser_get"
    },
    "email_list": {
        "name": "email_list",
        "description": "List emails from an IMAP mailbox. Returns subject, from, date, and UID for each.",
        "parameters": {
            "mailbox": {"type": "string", "description": "IMAP mailbox folder (e.g. 'INBOX')", "required": False, "default": "INBOX"},
            "count": {"type": "integer", "description": "Number of recent emails to fetch", "required": False, "default": 20},
            "search": {"type": "string", "description": "IMAP search criterion (e.g. 'UNSEEN', 'FROM \"someone@example.com\"', 'SINCE 01-Jan-2025')", "required": False, "default": ""}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.list_emails"
    },
    "email_read": {
        "name": "email_read",
        "description": "Read a specific email by UID from an IMAP mailbox. Returns full body and headers.",
        "parameters": {
            "uid": {"type": "integer", "description": "UID of the email to read", "required": True},
            "mailbox": {"type": "string", "description": "IMAP mailbox folder", "required": False, "default": "INBOX"}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.read_email"
    },
    "email_send": {
        "name": "email_send",
        "description": "Send an email via SMTP. Supports plain text and HTML bodies.",
        "parameters": {
            "to": {"type": "string", "description": "Recipient email address", "required": True},
            "subject": {"type": "string", "description": "Email subject line", "required": True},
            "body": {"type": "string", "description": "Email body text", "required": True},
            "html": {"type": "string", "description": "Optional HTML body", "required": False, "default": ""},
            "from_addr": {"type": "string", "description": "Sender address (defaults to configured account)", "required": False, "default": ""}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.send_email"
    },
    "email_search": {
        "name": "email_search",
        "description": "Search emails in an IMAP mailbox by criteria. Returns matching UIDs with subject/from/date.",
        "parameters": {
            "criteria": {"type": "string", "description": "IMAP search criteria (e.g. 'UNSEEN', 'FROM \"sender\"', 'SUBJECT \"meeting\"', 'SINCE 01-Jan-2025')", "required": True},
            "mailbox": {"type": "string", "description": "IMAP mailbox folder", "required": False, "default": "INBOX"}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.search_emails"
    },
    "google_search": {
        "name": "google_search",
        "description": "Search Google using the Custom Search API. Returns title, URL, and snippet for each result.",
        "parameters": {
            "query": {"type": "string", "description": "Search query", "required": True},
            "num": {"type": "integer", "description": "Number of results (1-10)", "required": False, "default": 5}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.search"
    },
    "google_gmail_read": {
        "name": "google_gmail_read",
        "description": "Read Gmail messages via Google API (requires OAuth). Returns snippet, from, date, and message ID.",
        "parameters": {
            "max_results": {"type": "integer", "description": "Max messages to retrieve", "required": False, "default": 10},
            "label_ids": {"type": "string", "description": "Gmail label (e.g. 'INBOX', 'UNREAD', 'STARRED')", "required": False, "default": "INBOX"},
            "query": {"type": "string", "description": "Gmail search query (e.g. 'from:boss is:unread')", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.gmail_read"
    },
    "google_gmail_send": {
        "name": "google_gmail_send",
        "description": "Send an email via Gmail API (requires OAuth). Returns the sent message ID.",
        "parameters": {
            "to": {"type": "string", "description": "Recipient email", "required": True},
            "subject": {"type": "string", "description": "Subject line", "required": True},
            "body": {"type": "string", "description": "Email body text", "required": True},
            "html": {"type": "string", "description": "Optional HTML body", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.gmail_send"
    },
    "google_calendar_list": {
        "name": "google_calendar_list",
        "description": "List upcoming Google Calendar events (requires OAuth).",
        "parameters": {
            "max_results": {"type": "integer", "description": "Max events to return", "required": False, "default": 10},
            "time_min": {"type": "string", "description": "Start time in ISO 8601 format (e.g. '2025-01-01T00:00:00-05:00')", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.calendar_list"
    },
    "google_calendar_create": {
        "name": "google_calendar_create",
        "description": "Create a Google Calendar event (requires OAuth).",
        "parameters": {
            "summary": {"type": "string", "description": "Event title", "required": True},
            "start_time": {"type": "string", "description": "Start time in ISO 8601 format", "required": True},
            "end_time": {"type": "string", "description": "End time in ISO 8601 format", "required": True},
            "description": {"type": "string", "description": "Event description", "required": False, "default": ""},
            "attendees": {"type": "string", "description": "Comma-separated list of attendee emails", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.calendar_create"
    },
    "google_drive_list": {
        "name": "google_drive_list",
        "description": "List files in Google Drive (requires OAuth).",
        "parameters": {
            "max_results": {"type": "integer", "description": "Max files to return", "required": False, "default": 20},
            "q": {"type": "string", "description": "Google Drive query (e.g. 'mimeType contains \"folder\"', 'name contains \"report\"')", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.drive_list"
    },
    "google_drive_upload": {
        "name": "google_drive_upload",
        "description": "Upload a local file to Google Drive (requires OAuth).",
        "parameters": {
            "file_path": {"type": "string", "description": "Local file path to upload", "required": True},
            "name": {"type": "string", "description": "Name for the file in Drive", "required": True},
            "parents": {"type": "string", "description": "Parent folder ID (optional)", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.drive_upload"
    },
    "shell_run": {
        "name": "shell_run",
        "description": "Execute a shell command and return stdout, stderr, and exit code.",
        "parameters": {
            "command": {"type": "string", "description": "Shell command to execute", "required": True},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "required": False, "default": 60}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.shell.run_command"
    },
    "shell_script": {
        "name": "shell_script",
        "description": "Write a script to a file and execute it. Returns stdout, stderr, and exit code.",
        "parameters": {
            "script": {"type": "string", "description": "Script content (bash or python)", "required": True},
            "language": {"type": "string", "description": "Script language: 'bash' or 'python'", "required": False, "default": "bash"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "required": False, "default": 120}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.shell.run_script"
    },
    "create_tool": {
        "name": "create_tool",
        "description": "Create a new persistent tool. The tool will be saved to the registry and available for all future conversations. Define the tool_name, description, parameters (as JSON), and handler_code (Python function).",
        "parameters": {
            "tool_name": {"type": "string", "description": "Unique name for the tool (lowercase, no spaces)", "required": True},
            "description": {"type": "string", "description": "What this tool does", "required": True},
            "parameters_json": {"type": "string", "description": "JSON object defining parameters, e.g. '{\"param1\": {\"type\": \"string\", \"description\": \"...\", \"required\": true}}'", "required": True},
            "handler_code": {"type": "string", "description": "Python function that implements the tool. Must accept **kwargs and return a string result.", "required": True}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.system.create_tool"
    },
    "list_tools": {
        "name": "list_tools",
        "description": "List all available tools with their names, descriptions, and parameters.",
        "parameters": {},
        "category": "system",
        "handler": "walbert.tools.builtins.system.list_tools"
    },
    "get_tool": {
        "name": "get_tool",
        "description": "Get the full definition of a specific tool by name.",
        "parameters": {
            "tool_name": {"type": "string", "description": "Name of the tool to look up", "required": True}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.system.get_tool"
    },
    "db_query": {
        "name": "db_query",
        "description": "Execute a SQL query against the Walbert SQLite database. Use for SELECT queries to read data, or INSERT/UPDATE/DELETE to modify data.",
        "parameters": {
            "db_path": {"type": "string", "description": "Path to the SQLite database file (default: 'instance/walbert.db')", "required": False, "default": "instance/walbert.db"},
            "sql": {"type": "string", "description": "SQL statement to execute", "required": True}
        },
        "category": "database",
        "handler": "walbert.tools.builtins.sql.execute_sql"
    },
    "python_execute": {
        "name": "python_execute",
        "description": "Execute Python code in a subprocess. Use for data processing, API calls, file operations, or any task requiring Python.",
        "parameters": {
            "code": {"type": "string", "description": "Python source code to execute", "required": True},
            "timeout": {"type": "integer", "description": "Maximum execution time in seconds (default: 60)", "required": False, "default": 60}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.python.execute_python"
    },
    "peer_send": {
        "name": "peer_send",
        "description": "Send a message to a peer Walbert instance on the network. Returns the peer's response.",
        "parameters": {
            "peer_ip": {"type": "string", "description": "IP address of the peer Walbert instance", "required": True},
            "message": {"type": "string", "description": "Message text to send to the peer", "required": True}
        },
        "category": "network",
        "handler": "walbert.tools.builtins.shell.peer_send"
    },
}


class ToolRegistry:
    """Manages the collection of available tools, persisted to disk."""

    def __init__(self, registry_path: str = "instance/tools/registry.json"):
        self.registry_path = registry_path
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Load tools from the persisted registry file."""
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)

        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    # Merge: built-in tools get defaults, user tools override
                    self._tools = {}
                    for name, tool in DEFAULT_TOOLS.items():
                        self._tools[name] = dict(tool)
                    # Overlay user-created tools
                    user_tools = data.get("custom_tools", {})
                    for name, tool in user_tools.items():
                        self._tools[name] = tool
                    logger.info(f"Loaded {len(self._tools)} tools from registry")
            except Exception as e:
                logger.error(f"Failed to load tool registry: {e}")
                self._tools = {name: dict(tool) for name, tool in DEFAULT_TOOLS.items()}
        else:
            # Write fresh registry with defaults
            self._tools = {name: dict(tool) for name, tool in DEFAULT_TOOLS.items()}
            self._save()
            logger.info(f"Created new tool registry with {len(self._tools)} default tools")

    def _save(self):
        """Persist the registry to disk (user tools only, built-ins are implicit)."""
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        custom = {name: tool for name, tool in self._tools.items()
                  if name not in DEFAULT_TOOLS or self._tools.get(name) != DEFAULT_TOOLS.get(name)}
        data = {"custom_tools": custom}
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """Get all available tools."""
        return dict(self._tools)

    def register_tool(self, tool_def: Dict[str, Any]) -> bool:
        """Register a new tool. tool_def must have 'name', 'description', 'parameters', 'handler'."""
        name = tool_def.get("name")
        if not name:
            logger.error("Tool definition missing 'name'")
            return False
        if name in DEFAULT_TOOLS and name not in self._tools:
            # Check if it's a fresh default (not user-modified)
            pass  # Allow shadowing if explicitly registered
        self._tools[name] = tool_def
        self._save()
        logger.info(f"Registered tool: {name}")
        return True

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in DEFAULT_TOOLS:
            logger.warning(f"Cannot unregister built-in tool: {name}")
            return False
        if name in self._tools:
            del self._tools[name]
            self._save()
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def to_prompt_format(self) -> str:
        """Format all tools for inclusion in the system prompt."""
        lines = ["\n---\n## Available Tools"]
        for name, tool in sorted(self._tools.items()):
            desc = tool.get("description", "")
            params = tool.get("parameters", {})
            param_str = ""
            if params:
                param_parts = []
                for pname, pdef in params.items():
                    required = pdef.get("required", False)
                    ptype = pdef.get("type", "string")
                    pdesc = pdef.get("description", "")
                    req_mark = " (required)" if required else ""
                    param_parts.append(f"  - {pname} ({ptype}){req_mark}: {pdesc}")
                param_str = "\n" + "\n".join(param_parts)
            lines.append(f"\n### {name}")
            lines.append(f"Description: {desc}")
            if param_str:
                lines.append(f"Parameters:{param_str}")
        lines.append("\n---\n")
        return "\n".join(lines)
