"""
Filesystem tools - read, write, list, search, delete, copy files.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Uses ensure_under_root for path security
- Proper error handling and logging
"""

import os
import shutil
import logging
from typing import List

from walbert.tools.base import BaseTool, ToolResult
from walbert.tools.security import ensure_under_root, truncate_tool_result

logger = logging.getLogger("walbert.tools.builtins.filesystem")


class ReadFileTool(BaseTool):
    name = "filesystem_read"
    description = "Read the contents of a file. Returns the full text content."
    parameters = {"path": "string"}

    def execute(self, params: dict) -> ToolResult:
        path = ensure_under_root(params["path"], self.root_dir)

        if not os.path.exists(path):
            return ToolResult(False, "", error=f"File not found: {params['path']}")

        if not os.path.isfile(path):
            return ToolResult(False, "", error=f"Not a file: {params['path']}")

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Truncate very large files
            if len(content) > 50000:
                content = f"# {params['path']}\n# (truncated, {len(content)} chars total, showing first 50000)\n{content[:50000]}\n...\n# End of file"

            return ToolResult(
                True, content,
                summary=f"{len(content)} chars, {len(content.splitlines())} lines"
            )
        except PermissionError:
            return ToolResult(False, "", error=f"Permission denied: {params['path']}")
        except Exception as e:
            return ToolResult(False, "", error=f"Error reading file: {e}")


class WriteFileTool(BaseTool):
    name = "filesystem_write"
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {"path": "string", "content": "string"}

    def execute(self, params: dict) -> ToolResult:
        path = ensure_under_root(params["path"], self.root_dir)

        try:
            # Create parent directories
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(params["content"])

            # Verify the write
            with open(path, 'r', encoding='utf-8') as f:
                written = f.read()
            if written != params["content"]:
                return ToolResult(False, "", error="File verification failed: written content does not match")

            return ToolResult(
                True, f"Successfully wrote {len(params['content'])} characters to {params['path']}",
                summary=f"Created/overwrote: {params['path']}",
                file_paths=[path]
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error writing file: {e}")


class ListDirectoryTool(BaseTool):
    name = "filesystem_list"
    description = "List files and directories in a directory."
    parameters = {"path": "string", "recursive": "string?"}

    def execute(self, params: dict) -> ToolResult:
        path = ensure_under_root(params["path"], self.root_dir)

        if not os.path.exists(path):
            return ToolResult(False, "", error=f"Directory not found: {params['path']}")

        if not os.path.isdir(path):
            return ToolResult(False, "", error=f"Not a directory: {params['path']}")

        recursive = params.get("recursive", "false").lower() in ("true", "1", "yes")
        entries = []

        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    rel = os.path.relpath(root, path)
                    indent = "  " * (root.count(os.sep) - path.count(os.sep))
                    if rel != '.':
                        entries.append(f"{indent}[DIR] {rel}/")
                    for f in sorted(files):
                        fp = os.path.join(root, f)
                        size = os.path.getsize(fp)
                        entries.append(f"{indent}  {f} ({size} bytes)")
            else:
                items = sorted(os.listdir(path))
                for item in items:
                    full = os.path.join(path, item)
                    if os.path.isdir(full):
                        entries.append(f"[DIR] {item}/")
                    else:
                        size = os.path.getsize(full)
                        entries.append(f"      {item} ({size} bytes)")
        except PermissionError:
            return ToolResult(False, "", error=f"Permission denied: {params['path']}")

        return ToolResult(
            True, f"# Contents of {params['path']} ({len(entries)} items)\n" + "\n".join(entries),
            summary=f"{len(entries)} items in {params['path']}"
        )


class SearchFilesTool(BaseTool):
    name = "filesystem_search"
    description = "Search for files matching a glob pattern in a directory tree."
    parameters = {"path": "string", "pattern": "string"}

    def execute(self, params: dict) -> ToolResult:
        import fnmatch
        path = ensure_under_root(params["path"], self.root_dir)

        if not os.path.exists(path):
            return ToolResult(False, "", error=f"Path not found: {params['path']}")

        matches = []
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    if fnmatch.fnmatch(f, params["pattern"]):
                        full = os.path.join(root, f)
                        size = os.path.getsize(full)
                        rel = os.path.relpath(full, path)
                        matches.append(f"  {rel} ({size} bytes)")
        except PermissionError:
            return ToolResult(False, "", error="Permission denied in some directories")

        if matches:
            return ToolResult(
                True, f"# Found {len(matches)} matches for '{params['pattern']}' in {params['path']}\n" + "\n".join(matches),
                summary=f"{len(matches)} matches for '{params['pattern']}'"
            )
        else:
            return ToolResult(True, f"No files matching '{params['pattern']}' found in {params['path']}")


class DeletePathTool(BaseTool):
    name = "filesystem_delete"
    description = "Delete a file or empty directory. Use with caution."
    parameters = {"path": "string"}

    def execute(self, params: dict) -> ToolResult:
        path = ensure_under_root(params["path"], self.root_dir)

        if not os.path.exists(path):
            return ToolResult(False, "", error=f"Path not found: {params['path']}")

        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
                return ToolResult(True, f"Deleted directory: {params['path']}", file_paths=[path])
            else:
                os.remove(path)
                return ToolResult(True, f"Deleted file: {params['path']}", file_paths=[path])
        except Exception as e:
            return ToolResult(False, "", error=f"Error deleting path: {e}")


class CopyFileTool(BaseTool):
    name = "filesystem_copy"
    description = "Copy a file from source to destination."
    parameters = {"src": "string", "dst": "string"}

    def execute(self, params: dict) -> ToolResult:
        src = ensure_under_root(params["src"], self.root_dir)
        dst = ensure_under_root(params["dst"], self.root_dir)

        if not os.path.exists(src):
            return ToolResult(False, "", error=f"Source not found: {params['src']}")

        try:
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(src, dst)
            size = os.path.getsize(dst)
            return ToolResult(
                True, f"Copied {params['src']} -> {params['dst']} ({size} bytes)",
                summary=f"Copied {params['src']} to {params['dst']}",
                file_paths=[dst]
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error copying file: {e}")


# ===================================================================
# Backward-compatible function wrappers (for handler-path references)
# ===================================================================

def read_file(path: str, **kwargs) -> str:
    """Legacy wrapper for ReadFileTool."""
    tool = ReadFileTool(kwargs.get("root_dir", ""))
    result = tool.execute({"path": path})
    return result.content if result.success else f"Error: {result.error}"


def write_file(path: str, content: str, **kwargs) -> str:
    """Legacy wrapper for WriteFileTool."""
    tool = WriteFileTool(kwargs.get("root_dir", ""))
    result = tool.execute({"path": path, "content": content})
    return result.content if result.success else f"Error: {result.error}"


def list_directory(path: str, recursive: str = "false", **kwargs) -> str:
    """Legacy wrapper for ListDirectoryTool."""
    tool = ListDirectoryTool(kwargs.get("root_dir", ""))
    result = tool.execute({"path": path, "recursive": recursive})
    return result.content if result.success else f"Error: {result.error}"


def search_files(path: str, pattern: str, **kwargs) -> str:
    """Legacy wrapper for SearchFilesTool."""
    tool = SearchFilesTool(kwargs.get("root_dir", ""))
    result = tool.execute({"path": path, "pattern": pattern})
    return result.content if result.success else f"Error: {result.error}"


def delete_path(path: str, **kwargs) -> str:
    """Legacy wrapper for DeletePathTool."""
    tool = DeletePathTool(kwargs.get("root_dir", ""))
    result = tool.execute({"path": path})
    return result.content if result.success else f"Error: {result.error}"


def copy_file(src: str, dst: str, **kwargs) -> str:
    """Legacy wrapper for CopyFileTool."""
    tool = CopyFileTool(kwargs.get("root_dir", ""))
    result = tool.execute({"src": src, "dst": dst})
    return result.content if result.success else f"Error: {result.error}"
