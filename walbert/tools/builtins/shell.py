"""
System tools - shell execution and tool management.
"""

import os
import json
import logging
import subprocess
import tempfile
import sys
from typing import Dict, Any, Optional

logger = logging.getLogger("walbert.tools.builtins.shell")

# Module-level reference to the NetworkManager instance.
# Set by the agent during initialization so peer_send can use it.
_comms = None


def set_comms(comms_manager):
    """Set the NetworkManager instance for peer communication tools."""
    global _comms
    _comms = comms_manager


def get_comms():
    """Get the current NetworkManager instance."""
    return _comms


def peer_send(peer_ip: str, message: str, **kwargs) -> str:
    """Send a message to a peer Walbert instance.
    
    Args:
        peer_ip: IP address of the peer Walbert instance.
        message: Message text to send.
    """
    comms = get_comms()
    if comms is None:
        return "Error: Peer communication is not enabled. Enable it via config or the enable_peer_communication tool."
    
    result = comms.send_to_peer(peer_ip, message)
    if result is None:
        return f"Error: Failed to send message to {peer_ip} (connection refused or timed out)"
    
    return f"Message sent to {peer_ip}.\nResponse: {result}"


def run_command(command: str, timeout: int = 60, **kwargs) -> str:
    """Execute a shell command."""
    try:
        timeout = int(timeout) if isinstance(timeout, str) else timeout
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        output_parts.append(f"Exit code: {result.returncode}")
        
        return "\n".join(output_parts)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {e}"


def run_script(script: str, language: str = "bash", timeout: int = 120, **kwargs) -> str:
    """Write a script to a temp file and execute it."""
    try:
        timeout = int(timeout) if isinstance(timeout, str) else timeout
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix=f".{'py' if language == 'python' else '.sh'}",
            delete=False
        ) as f:
            f.write(script)
            script_path = f.name
        
        if language == "python":
            cmd = [sys.executable, script_path]
        else:
            cmd = ["bash", script_path]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        os.unlink(script_path)
        
        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        output_parts.append(f"Exit code: {result.returncode}")
        
        return "\n".join(output_parts)
    except Exception as e:
        return f"Error running script: {e}"


def create_tool(tool_name: str, description: str, parameters_json: str, handler_code: str, **kwargs) -> str:
    """Create a new persistent tool in the registry."""
    try:
        # Parse parameters JSON
        params = json.loads(parameters_json)
        
        # Validate tool name
        if not tool_name or not tool_name.replace('_', '').isalnum():
            return f"Error: Invalid tool name '{tool_name}'. Use lowercase letters, numbers, and underscores only."
        
        if tool_name in ("create_tool", "list_tools", "get_tool"):
            return f"Error: '{tool_name}' is a reserved tool name."
        
        # Store the handler code in a persistent module
        # Resolve paths relative to the Walbert project root
        walbert_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        # Handler files go in walbert/instance_tools/ so they can be imported as walbert.instance_tools.{name}
        pkg_dir = os.path.join(walbert_root, "walbert", "instance_tools")
        os.makedirs(pkg_dir, exist_ok=True)
        handler_file = os.path.join(pkg_dir, f"{tool_name}.py")
        
        # Also copy to instance/tools/ for user auditing
        audit_dir = os.path.join(walbert_root, "instance", "tools")
        os.makedirs(audit_dir, exist_ok=True)
        audit_file = os.path.join(audit_dir, f"{tool_name}.py")
        handler_module = f"walbert.instance_tools.{tool_name}"
        
        handler_content = f'''"""Auto-generated tool: {tool_name}"""

def run(**kwargs):
    """Auto-generated handler for {tool_name}.
    Parameters: {json.dumps(params, indent=4)}
    """
{handler_code}
'''
        with open(handler_file, 'w') as f:
            f.write(handler_content)
        
        # Copy to audit directory
        with open(audit_file, 'w') as f:
            f.write(handler_content)
        
        # Create __init__.py for the instance_tools package
        init_file = os.path.join(pkg_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                f.write('')
        
        # Add walbert/ to sys.path so walbert.instance_tools can be imported
        walbert_dir = os.path.join(walbert_root, "walbert")
        if walbert_dir not in sys.path:
            sys.path.insert(0, walbert_dir)
        
        # Validate the handler can be imported and has a callable 'run' function
        import importlib
        # Remove cached module if exists
        if handler_module in sys.modules:
            del sys.modules[handler_module]
        
        try:
            mod = importlib.import_module(handler_module)
            if not hasattr(mod, 'run') or not callable(getattr(mod, 'run')):
                return f"Error: Handler must have a callable 'run' function. Add 'def run(**kwargs): ...' to your code."
        except Exception as e:
            # Clean up on failure
            try:
                os.unlink(handler_file)
            except:
                pass
            return f"Error: Handler code validation failed: {e}"
        
        # Register the tool in the registry
        from walbert.tools.registry import ToolRegistry
        registry = ToolRegistry(f"{walbert_root}/instance/tools/registry.json")
        
        tool_def = {
            "name": tool_name,
            "description": description,
            "parameters": params,
            "category": "custom",
            "handler": f"{handler_module}.run"
        }
        
        registry.register_tool(tool_def)
        
        return f"Tool '{tool_name}' created successfully!\n\nDefinition:\n  Name: {tool_name}\n  Description: {description}\n  Parameters: {json.dumps(params, indent=2)}\n  Handler: {tool_def['handler']}\n  Audit file: {audit_file}\n\nThe tool is saved and can be audited/edited at any time."
    except json.JSONDecodeError as e:
        return f"Error: Invalid parameters JSON: {e}"
    except Exception as e:
        return f"Error creating tool: {e}"


def list_tools(**kwargs) -> str:
    """List all available tools."""
    from walbert.tools.registry import ToolRegistry
    registry = ToolRegistry()
    tools = registry.list_tools()
    
    output = ["# Available Tools\n"]
    for name, tool in sorted(tools.items()):
        desc = tool.get("description", "")
        params = tool.get("parameters", {})
        param_list = []
        for pname, pdef in params.items():
            required = pdef.get("required", False)
            ptype = pdef.get("type", "string")
            param_list.append(f"  - {pname} ({ptype}){' [required]' if required else ''}")
        
        output.append(f"\n## {name}")
        output.append(f"Description: {desc}")
        if param_list:
            output.append(f"Parameters:\n" + "\n".join(param_list))
        if tool.get("category"):
            output.append(f"Category: {tool['category']}")
    
    output.append(f"\n\nTotal: {len(tools)} tools")
    return "\n".join(output)


def get_tool(tool_name: str, **kwargs) -> str:
    """Get the full definition of a specific tool."""
    from walbert.tools.registry import ToolRegistry
    registry = ToolRegistry()
    tool = registry.get_tool(tool_name)
    
    if not tool:
        return f"Error: Tool '{tool_name}' not found."
    
    return json.dumps(tool, indent=2)
