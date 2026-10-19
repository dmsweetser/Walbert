"""
Filesystem tools - read, write, list, search, delete, copy files.
"""

import os
import shutil
import logging
from typing import List

logger = logging.getLogger("walbert.tools.builtins.filesystem")


def read_file(path: str, **kwargs) -> str:
    """Read the contents of a file."""
    # Resolve relative paths against working directory
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    
    if not os.path.isfile(path):
        return f"Error: Not a file: {path}"
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Truncate very large files
        if len(content) > 50000:
            return f"# {path}\n# (truncated, {len(content)} chars total, showing first 50000)\n{content[:50000]}\n...\n# End of file"
        
        return f"# {path}\n{content}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except UnicodeDecodeError:
        return f"Error: File is binary or non-UTF-8: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(path: str, content: str, **kwargs) -> str:
    """Write content to a file."""
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    try:
        # Create parent directories
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def list_directory(path: str, recursive: bool = False, **kwargs) -> str:
    """List files and directories in a directory."""
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    if not os.path.exists(path):
        return f"Error: Directory not found: {path}"
    
    if not os.path.isdir(path):
        return f"Error: Not a directory: {path}"
    
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
        return f"Error: Permission denied: {path}"
    
    return f"# Contents of {path} ({len(entries)} items)\n" + "\n".join(entries)


def search_files(path: str, pattern: str, **kwargs) -> str:
    """Search for files matching a glob pattern."""
    import fnmatch
    
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    if not os.path.exists(path):
        return f"Error: Path not found: {path}"
    
    matches = []
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    full = os.path.join(root, f)
                    size = os.path.getsize(full)
                    rel = os.path.relpath(full, path)
                    matches.append(f"  {rel} ({size} bytes)")
    except PermissionError:
        return f"Error: Permission denied in some directories"
    
    if matches:
        return f"# Found {len(matches)} matches for '{pattern}' in {path}\n" + "\n".join(matches)
    else:
        return f"No files matching '{pattern}' found in {path}"


def delete_path(path: str, **kwargs) -> str:
    """Delete a file or empty directory."""
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    if not os.path.exists(path):
        return f"Error: Path not found: {path}"
    
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
            return f"Deleted directory: {path}"
        else:
            os.remove(path)
            return f"Deleted file: {path}"
    except Exception as e:
        return f"Error deleting path: {e}"


def copy_file(src: str, dst: str, **kwargs) -> str:
    """Copy a file from source to destination."""
    if not os.path.isabs(src):
        src = os.path.join(os.getcwd(), src)
    if not os.path.isabs(dst):
        dst = os.path.join(os.getcwd(), dst)
    
    if not os.path.exists(src):
        return f"Error: Source not found: {src}"
    
    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        return f"Copied {src} -> {dst} ({size} bytes)"
    except Exception as e:
        return f"Error copying file: {e}"
