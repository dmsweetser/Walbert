"""
System tools - shell execution and tool management.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Uses ensure_under_root for path security
- Proper error handling and logging
"""

import os
import json
import logging
import subprocess
import tempfile
import sys
from typing import Dict, Any, Optional

from walbert.tools.base import BaseTool, ToolResult
from walbert.tools.security import ensure_under_root, validate_tool_params

logger = logging.getLogger("walbert.tools.builtins.shell")

# Module-level reference to the NetworkManager instance.
_comms = None


def set_comms(comms_manager):
    """Set the NetworkManager instance for peer communication tools."""
    global _comms
    _comms = comms_manager


def get_comms():
    """Get the current NetworkManager instance."""
    return _comms


class ShellRunTool(BaseTool):
    name = "shell_run"
    description = "Execute a shell command and return stdout, stderr, and exit code."
    parameters = {"command": "string", "timeout": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            timeout = int(params.get("timeout", "60")) if params.get("timeout") else 60
            result = subprocess.run(
                params["command"],
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

            return ToolResult(
                True, "\n".join(output_parts),
                summary=f"Command exited with code {result.returncode}"
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", error=f"Command timed out after {params.get('timeout', 60)} seconds")
        except Exception as e:
            return ToolResult(False, "", error=f"Error executing command: {e}")


class ShellScriptTool(BaseTool):
    name = "shell_script"
    description = "Write a script to a file and execute it."
    parameters = {"script": "string", "language": "string?", "timeout": "string?"}

    def execute(self, params: dict) -> ToolResult:
        script_path = None
        try:
            timeout = int(params.get("timeout", "120")) if params.get("timeout") else 120
            language = params.get("language", "bash")

            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=f".{'py' if language == 'python' else '.sh'}",
                delete=False
            ) as f:
                f.write(params["script"])
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

            output_parts = []
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            output_parts.append(f"Exit code: {result.returncode}")

            return ToolResult(
                True, "\n".join(output_parts),
                summary=f"Script exited with code {result.returncode}"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error running script: {e}")
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass


class PeerSendTool(BaseTool):
    name = "peer_send"
    description = "Send a message to a peer Walbert instance on the network."
    parameters = {"peer_ip": "string", "message": "string"}

    def execute(self, params: dict) -> ToolResult:
        comms = get_comms()
        if comms is None:
            return ToolResult(False, "", error="Peer communication is not enabled.")

        result = comms.send_to_peer(params["peer_ip"], params["message"])
        if result is None:
            return ToolResult(False, "", error=f"Failed to send message to {params['peer_ip']}")

        return ToolResult(
            True, f"Message sent to {params['peer_ip']}.\nResponse: {result}",
            summary=f"Sent message to {params['peer_ip']}"
        )


# ===================================================================
# Backward-compatible function wrappers
# ===================================================================

def run_command(command: str, timeout: str = "60", **kwargs) -> str:
    """Legacy wrapper for ShellRunTool."""
    tool = ShellRunTool(kwargs.get("root_dir", ""))
    result = tool.execute({"command": command, "timeout": timeout})
    return result.content if result.success else f"Error: {result.error}"


def run_script(script: str, language: str = "bash", timeout: str = "120", **kwargs) -> str:
    """Legacy wrapper for ShellScriptTool."""
    tool = ShellScriptTool(kwargs.get("root_dir", ""))
    result = tool.execute({"script": script, "language": language, "timeout": timeout})
    return result.content if result.success else f"Error: {result.error}"


def peer_send(peer_ip: str, message: str, **kwargs) -> str:
    """Legacy wrapper for PeerSendTool."""
    tool = PeerSendTool(kwargs.get("root_dir", ""))
    result = tool.execute({"peer_ip": peer_ip, "message": message})
    return result.content if result.success else f"Error: {result.error}"


class CreateToolTool(BaseTool):
    name = "create_tool"
    description = "Create a new persistent tool in the registry."
    parameters = {
        "tool_name": "string",
        "description": "string",
        "parameters_json": "string",
        "handler_code": "string"
    }

    def execute(self, params: dict) -> ToolResult:
        try:
            # Parse parameters JSON
            tool_params = json.loads(params["parameters_json"])

            # Validate tool name
            if not params["tool_name"] or not params["tool_name"].replace('_', '').isalnum():
                return ToolResult(False, "", error=f"Invalid tool name '{params['tool_name']}'. Use lowercase letters, numbers, and underscores only.")

            if params["tool_name"] in ("create_tool", "list_tools", "get_tool"):
                return ToolResult(False, "", error=f"'{params['tool_name']}' is a reserved tool name.")

            # Store the handler code
            walbert_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

            pkg_dir = os.path.join(walbert_root, "walbert", "instance_tools")
            os.makedirs(pkg_dir, exist_ok=True)
            handler_file = os.path.join(pkg_dir, f"{params['tool_name']}.py")

            audit_dir = os.path.join(walbert_root, "instance", "tools")
            os.makedirs(audit_dir, exist_ok=True)
            audit_file = os.path.join(audit_dir, f"{params['tool_name']}.py")
            handler_module = f"walbert.instance_tools.{params['tool_name']}"

            handler_content = f'''"""Auto-generated tool: {params['tool_name']}"""

def run(**kwargs):
    """Auto-generated handler for {params['tool_name']}.
    Parameters: {json.dumps(tool_params, indent=4)}
    """
{params['handler_code']}
'''
            with open(handler_file, 'w') as f:
                f.write(handler_content)

            with open(audit_file, 'w') as f:
                f.write(handler_content)

            # Create __init__.py
            init_file = os.path.join(pkg_dir, "__init__.py")
            if not os.path.exists(init_file):
                with open(init_file, 'w') as f:
                    f.write('')

            # Add to sys.path
            walbert_dir = os.path.join(walbert_root, "walbert")
            if walbert_dir not in sys.path:
                sys.path.insert(0, walbert_dir)

            # Validate handler
            import importlib
            if handler_module in sys.modules:
                del sys.modules[handler_module]

            try:
                mod = importlib.import_module(handler_module)
                if not hasattr(mod, 'run') or not callable(getattr(mod, 'run')):
                    return ToolResult(False, "", error="Handler must have a callable 'run' function.")
            except Exception as e:
                try:
                    os.unlink(handler_file)
                except:
                    pass
                return ToolResult(False, "", error=f"Handler code validation failed: {e}")

            # Register in registry
            from walbert.tools.registry import ToolRegistry
            registry = ToolRegistry(f"{walbert_root}/instance/tools/registry.json")

            tool_def = {
                "name": params["tool_name"],
                "description": params["description"],
                "parameters": tool_params,
                "category": "custom",
                "handler": f"{handler_module}.run"
            }

            registry.register_tool(tool_def)

            return ToolResult(
                True,
                f"Tool '{params['tool_name']}' created successfully!\n\n"
                f"Definition:\n"
                f"  Name: {params['tool_name']}\n"
                f"  Description: {params['description']}\n"
                f"  Parameters: {json.dumps(tool_params, indent=2)}\n"
                f"  Handler: {tool_def['handler']}\n"
                f"  Audit file: {audit_file}\n\n"
                f"The tool is saved and can be audited/edited at any time.",
                summary=f"Created tool: {params['tool_name']}",
                file_paths=[handler_file, audit_file]
            )
        except json.JSONDecodeError as e:
            return ToolResult(False, "", error=f"Invalid parameters JSON: {e}")
        except Exception as e:
            return ToolResult(False, "", error=f"Error creating tool: {e}")


def list_tools(**kwargs) -> str:
    """List all available tools."""
    from walbert.tools.registry import ToolRegistry
    registry = ToolRegistry()
    tools = registry.list_tools()

    output = ["# Available Tools\n"]
    for tool in tools:
        desc = tool.get("description", "")
        params = tool.get("parameters", {})
        param_list = []
        for pname, pdef in params.items():
            if isinstance(pdef, dict):
                required = pdef.get("required", False)
                ptype = pdef.get("type", "string")
            else:
                required = False
                ptype = str(pdef)
            param_list.append(f"  - {pname} ({ptype}){' [required]' if required else ''}")

        output.append(f"\n## {tool['name']}")
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


def create_tool(tool_name: str, description: str, parameters_json: str, handler_code: str, **kwargs) -> str:
    """Legacy wrapper for CreateToolTool."""
    tool = CreateToolTool(kwargs.get("root_dir", ""))
    result = tool.execute({
        "tool_name": tool_name,
        "description": description,
        "parameters_json": parameters_json,
        "handler_code": handler_code
    })
    return result.content if result.success else f"Error: {result.error}"
