"""
Tool Registry - Manages the collection of available tools.

Adopted from AI-Builder engine best practices:
- Supports both class-based tools (BaseTool subclasses) and legacy handler-path tools
- Dynamic tool loading from approved pending tools
- get_definition() for LLM prompt generation
- Thread-safe persistence
"""

import json
import os
import logging
import importlib
import uuid
import sys
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field

from walbert.tools.base import BaseTool, ToolResult
from walbert.tools.security import ToolError, EngineError

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
            "headers": {"type": "string", "description": "JSON headers dict", "required": False, "default": ""}
        },
        "category": "web",
        "handler": "walbert.tools.builtins.web.http_post"
    },
    "web_browser": {
        "name": "web_browser",
        "description": "Navigate to a URL and extract page content as text. Handles JavaScript-rendered pages.",
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
            "mailbox": {"type": "string", "description": "IMAP mailbox folder", "required": False, "default": "INBOX"},
            "count": {"type": "integer", "description": "Number of recent emails to fetch", "required": False, "default": 20},
            "search": {"type": "string", "description": "IMAP search criterion", "required": False, "default": ""}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.list_emails"
    },
    "email_read": {
        "name": "email_read",
        "description": "Read a specific email by UID from an IMAP mailbox.",
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
            "from_addr": {"type": "string", "description": "Sender address", "required": False, "default": ""}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.send_email"
    },
    "email_search": {
        "name": "email_search",
        "description": "Search emails in an IMAP mailbox by criteria.",
        "parameters": {
            "criteria": {"type": "string", "description": "IMAP search criteria", "required": True},
            "mailbox": {"type": "string", "description": "IMAP mailbox folder", "required": False, "default": "INBOX"}
        },
        "category": "email",
        "handler": "walbert.tools.builtins.email.search_emails"
    },
    "google_search": {
        "name": "google_search",
        "description": "Search Google using the Custom Search API.",
        "parameters": {
            "query": {"type": "string", "description": "Search query", "required": True},
            "num": {"type": "integer", "description": "Number of results (1-10)", "required": False, "default": 5}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.search"
    },
    "google_gmail_read": {
        "name": "google_gmail_read",
        "description": "Read Gmail messages via Google API (requires OAuth).",
        "parameters": {
            "max_results": {"type": "integer", "description": "Max messages to retrieve", "required": False, "default": 10},
            "label_ids": {"type": "string", "description": "Gmail label", "required": False, "default": "INBOX"},
            "query": {"type": "string", "description": "Gmail search query", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.gmail_read"
    },
    "google_gmail_send": {
        "name": "google_gmail_send",
        "description": "Send an email via Gmail API (requires OAuth).",
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
            "time_min": {"type": "string", "description": "Start time in ISO 8601 format", "required": False, "default": ""}
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
            "attendees": {"type": "string", "description": "Comma-separated attendee emails", "required": False, "default": ""}
        },
        "category": "google",
        "handler": "walbert.tools.builtins.google.calendar_create"
    },
    "google_drive_list": {
        "name": "google_drive_list",
        "description": "List files in Google Drive (requires OAuth).",
        "parameters": {
            "max_results": {"type": "integer", "description": "Max files to return", "required": False, "default": 20},
            "q": {"type": "string", "description": "Google Drive query", "required": False, "default": ""}
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
            "parents": {"type": "string", "description": "Parent folder ID", "required": False, "default": ""}
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
        "description": "Create a new persistent tool. The tool will be saved and available for all future conversations.",
        "parameters": {
            "tool_name": {"type": "string", "description": "Unique name (lowercase, no spaces)", "required": True},
            "description": {"type": "string", "description": "What this tool does", "required": True},
            "parameters_json": {"type": "string", "description": "JSON object defining parameters", "required": True},
            "handler_code": {"type": "string", "description": "Python function that implements the tool", "required": True}
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
        "description": "Execute a SQL query against the Walbert SQLite database.",
        "parameters": {
            "db_path": {"type": "string", "description": "Path to SQLite database", "required": False, "default": "instance/walbert.db"},
            "sql": {"type": "string", "description": "SQL statement to execute", "required": True}
        },
        "category": "database",
        "handler": "walbert.tools.builtins.sql.execute_sql"
    },
    "python_execute": {
        "name": "python_execute",
        "description": "Execute Python code in a subprocess.",
        "parameters": {
            "code": {"type": "string", "description": "Python source code to execute", "required": True},
            "timeout": {"type": "integer", "description": "Max execution time in seconds", "required": False, "default": 60}
        },
        "category": "system",
        "handler": "walbert.tools.builtins.python.execute_python"
    },
    "peer_send": {
        "name": "peer_send",
        "description": "Send a message to a peer Walbert instance on the network.",
        "parameters": {
            "peer_ip": {"type": "string", "description": "IP address of the peer", "required": True},
            "message": {"type": "string", "description": "Message text to send", "required": True}
        },
        "category": "network",
        "handler": "walbert.tools.builtins.shell.peer_send"
    },
}


class ToolRegistry:
    """Manages the collection of available tools, persisted to disk.

    Supports:
    - Class-based tools (BaseTool subclasses)
    - Legacy handler-path tools (function references)
    - Dynamic tool loading from approved pending tools
    - Thread-safe persistence
    """

    def __init__(self, registry_path: str = "instance/tools/registry.json"):
        self.registry_path = registry_path
        self._tools: Dict[str, Any] = {}  # name -> BaseTool or handler-path dict
        self._handler_paths: Dict[str, str] = {}  # name -> handler path string
        self._load()

    def _load(self):
        """Load tools from the persisted registry file."""
        os.makedirs(os.path.dirname(self.registry_path) if os.path.dirname(self.registry_path) else ".", exist_ok=True)

        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    # Merge: built-in tools get defaults, user tools override
                    self._tools = {}
                    self._handler_paths = {}
                    for name, tool in DEFAULT_TOOLS.items():
                        self._tools[name] = tool
                        if "handler" in tool:
                            self._handler_paths[name] = tool["handler"]
                    # Overlay user-created tools
                    user_tools = data.get("custom_tools", {})
                    for name, tool in user_tools.items():
                        self._tools[name] = tool
                        if "handler" in tool:
                            self._handler_paths[name] = tool["handler"]
                    logger.info(f"Loaded {len(self._tools)} tools from registry")
            except Exception as e:
                logger.error(f"Failed to load tool registry: {e}")
                self._tools = {name: dict(tool) for name, tool in DEFAULT_TOOLS.items()}
                self._handler_paths = {name: tool["handler"] for name, tool in DEFAULT_TOOLS.items() if "handler" in tool}
        else:
            self._tools = {name: dict(tool) for name, tool in DEFAULT_TOOLS.items()}
            self._handler_paths = {name: tool["handler"] for name, tool in DEFAULT_TOOLS.items() if "handler" in tool}
            self._save()
            logger.info(f"Created new tool registry with {len(self._tools)} default tools")

    def _save(self):
        """Persist the registry to disk (user tools only)."""
        os.makedirs(os.path.dirname(self.registry_path) if os.path.dirname(self.registry_path) else ".", exist_ok=True)
        custom = {name: tool for name, tool in self._tools.items()
                  if name not in DEFAULT_TOOLS or self._tools.get(name) != DEFAULT_TOOLS.get(name)}
        data = {"custom_tools": custom}
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)

    def register_class_tool(self, tool_instance: BaseTool):
        """Register a class-based tool (BaseTool subclass instance)."""
        self._tools[tool_instance.name] = tool_instance
        if tool_instance.name in self._handler_paths:
            del self._handler_paths[tool_instance.name]
        logger.info(f"Registered class tool: {tool_instance.name}")

    def get_tool(self, name: str) -> Optional[Any]:
        """Get a tool by name. Returns the tool instance or definition dict."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Get all available tool definitions for the LLM prompt.

        Handles both class-based tools (calls get_definition()) and
        legacy handler-path tools (extracts from dict).
        """
        result = []
        for name, tool in sorted(self._tools.items()):
            if isinstance(tool, BaseTool):
                result.append(tool.get_definition())
            elif isinstance(tool, dict):
                params = tool.get("parameters", {})
                param_list = {}
                for pname, pdef in params.items():
                    if isinstance(pdef, dict):
                        param_list[pname] = pdef.get("type", "string")
                    else:
                        param_list[pname] = str(pdef)
                result.append({
                    "name": tool.get("name", name),
                    "description": tool.get("description", ""),
                    "parameters": param_list,
                })
        return result

    def list_tools_raw(self) -> Dict[str, Dict[str, Any]]:
        """Get all tools as raw dicts (for internal use)."""
        return dict(self._tools)

    def register_tool(self, tool_def: Dict[str, Any]) -> bool:
        """Register a new tool definition.

        Supports both class-based tools and handler-path definitions.
        """
        name = tool_def.get("name")
        if not name:
            logger.error("Tool definition missing 'name'")
            return False

        # Check if it's a class-based tool
        if "instance" in tool_def:
            self._tools[name] = tool_def["instance"]
            if name in self._handler_paths:
                del self._handler_paths[name]
        else:
            self._tools[name] = tool_def
            if "handler" in tool_def:
                self._handler_paths[name] = tool_def["handler"]

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
            if name in self._handler_paths:
                del self._handler_paths[name]
            self._save()
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def to_prompt_format(self) -> str:
        """Format all tools for inclusion in the system prompt."""
        lines = ["\n---\n## Available Tools"]
        for name, tool in sorted(self._tools.items()):
            if isinstance(tool, BaseTool):
                desc = tool.description
                params = tool.parameters
            elif isinstance(tool, dict):
                desc = tool.get("description", "")
                params = tool.get("parameters", {})
            else:
                continue

            param_str = ""
            if params:
                param_parts = []
                for pname, pdef in params.items():
                    if isinstance(pdef, dict):
                        required = pdef.get("required", False)
                        ptype = pdef.get("type", "string")
                        pdesc = pdef.get("description", "")
                    else:
                        required = False
                        ptype = str(pdef)
                        pdesc = ""
                    req_mark = " (required)" if required else ""
                    param_parts.append(f"  - {pname} ({ptype}){req_mark}: {pdesc}")
                param_str = "\n" + "\n".join(param_parts)
            lines.append(f"\n### {name}")
            lines.append(f"Description: {desc}")
            if param_str:
                lines.append(f"Parameters:{param_str}")
        lines.append("\n---\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Dynamic tool loading (approved from pending)
    # ------------------------------------------------------------------

    def _pending_tools_file(self) -> str:
        """Return the global pending tools file path."""
        # Use instance directory for pending tools
        instance_dir = os.path.dirname(self.registry_path)
        if not instance_dir:
            instance_dir = "instance"
        return os.path.join(instance_dir, "pending_tools.json")

    def load_approved_tools(self):
        """Load any previously-approved dynamic tools from disk."""
        pending_file = self._pending_tools_file()
        if not os.path.exists(pending_file):
            return

        try:
            with open(pending_file, 'r') as f:
                pending_tools = json.load(f)
        except Exception:
            return

        for entry in pending_tools:
            if entry.get("status") == "approved":
                self._register_dynamic_tool(entry)

    def get_pending_tools(self) -> List[Dict[str, Any]]:
        """Return all pending (awaiting approval) tools."""
        pending_file = self._pending_tools_file()
        if not os.path.exists(pending_file):
            return []
        try:
            with open(pending_file, 'r') as f:
                pending_tools = json.load(f)
            return [t for t in pending_tools if t.get("status") == "pending"]
        except Exception:
            return []

    def approve_tool(self, tool_id: str) -> Dict[str, Any]:
        """Approve a pending tool: mark it approved and register it."""
        pending_file = self._pending_tools_file()
        pending_tools = []
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r') as f:
                    pending_tools = json.load(f)
            except Exception:
                pending_tools = []

        for entry in pending_tools:
            if entry.get("id") == tool_id and entry.get("status") == "pending":
                entry["status"] = "approved"
                entry["approved_at"] = __import__("datetime").datetime.now().isoformat()
                with open(pending_file, 'w') as f:
                    json.dump(pending_tools, f, indent=2)
                self._register_dynamic_tool(entry)
                return {"status": "approved", "tool_id": tool_id, "tool_name": entry["name"]}

        return {"status": "not_found", "tool_id": tool_id}

    def reject_tool(self, tool_id: str) -> Dict[str, Any]:
        """Reject a pending tool: mark it rejected and unregister if loaded."""
        pending_file = self._pending_tools_file()
        pending_tools = []
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r') as f:
                    pending_tools = json.load(f)
            except Exception:
                pending_tools = []

        for entry in pending_tools:
            if entry.get("id") == tool_id and entry.get("status") == "pending":
                entry["status"] = "rejected"
                entry["rejected_at"] = __import__("datetime").datetime.now().isoformat()
                with open(pending_file, 'w') as f:
                    json.dump(pending_tools, f, indent=2)
                self._tools.pop(entry["name"], None)
                self._handler_paths.pop(entry["name"], None)
                return {"status": "rejected", "tool_id": tool_id, "tool_name": entry["name"]}

        return {"status": "not_found", "tool_id": tool_id}

    def _register_dynamic_tool(self, entry: Dict[str, Any]):
        """Register a dynamically-created tool from a pending entry.

        Supports two code styles:
        1. Class-based: defines a Tool class inheriting from BaseTool.
        2. Function-based: defines an execute(**kwargs) function.
        """
        tool_name = entry["name"]

        # Check if already registered
        if tool_name in self._tools:
            return

        tool_code = entry.get("code", "")
        if not tool_code:
            return

        # Build a namespace with all required names
        ns = {
            '__name__': f'_dynamic_tool_{uuid.uuid4().hex[:8]}',
            '__builtins__': __builtins__,
            'BaseTool': BaseTool,
            'ToolResult': ToolResult,
            'ToolError': ToolError,
            'os': __import__('os'),
            'json': __import__('json'),
            're': __import__('re'),
            'subprocess': __import__('subprocess'),
            'tempfile': __import__('tempfile'),
            'shutil': __import__('shutil'),
            'threading': __import__('threading'),
            'datetime': __import__('datetime'),
        }

        try:
            exec(tool_code, ns)
        except Exception as e:
            logging.warning(f"Failed to execute dynamic tool code: {e}")
            return

        # Try class-based approach first
        tool_cls = ns.get('Tool')
        if tool_cls and isinstance(tool_cls, type) and issubclass(tool_cls, BaseTool):
            try:
                tool_instance = tool_cls("")
                self._tools[tool_name] = tool_instance
                logger.info(f"Registered dynamic class tool: {tool_name}")
                return
            except Exception as e:
                logging.warning(f"Failed to instantiate dynamic tool class: {e}")

        # Fallback: function-based execute(**kwargs) wrapper
        execute_fn = ns.get('execute')
        if callable(execute_fn):
            class _DynamicFunctionTool(BaseTool):
                """Wrapper for function-based dynamic tools."""
                name = tool_name
                description = entry.get("description", "")
                parameters = entry.get("parameters", {})

                def __init__(self, root_dir: str = ""):
                    super().__init__(root_dir)
                    self._execute_fn = execute_fn

                def execute(self, params: Dict[str, Any]) -> ToolResult:
                    try:
                        result = self._execute_fn(params=params)
                        if isinstance(result, ToolResult):
                            return result
                        return ToolResult(
                            success=True,
                            content=str(result),
                            summary=f"Executed {self.name}",
                        )
                    except Exception as e:
                        return ToolResult(
                            success=False,
                            content="",
                            error=str(e),
                            summary=f"Failed to execute {self.name}",
                        )

            try:
                tool_instance = _DynamicFunctionTool("")
                self._tools[tool_name] = tool_instance
                logger.info(f"Registered dynamic function tool: {tool_name}")
                return
            except Exception as e:
                logging.warning(f"Failed to instantiate function-based dynamic tool: {e}")
