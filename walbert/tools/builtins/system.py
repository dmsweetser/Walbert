"""
System tools - tool management and user interaction.

Imported from walbert.tools.builtins.shell for backwards compat.
"""
from walbert.tools.builtins.shell import create_tool, list_tools, get_tool

# New: request_user_input tool (AI-Builder pattern)
class RequestUserInputTool:
    """Tool to request interactive user input during agent execution.
    
    Uses the status file system (status.json) for communication.
    The UI should write the answer to status.json as:
        {"pending_user_input": {"question": "...", "answer": "..."}}
    """
    name = "request_user_input"
    description = (
        "Request interactive input from the user. The agent will pause "
        "and wait for the user to respond. Use this when you need human "
        "clarification or approval before proceeding."
    )
    parameters = {
        "question": "string",
        "timeout": "string?",
    }

    def __init__(self, root_dir: str = "", status_dir: str = ""):
        self.root_dir = root_dir
        self.status_dir = status_dir

    def execute(self, params: dict) -> dict:
        """Execute the request_user_input tool."""
        try:
            from walbert.status_file import set_pending_user_input

            question = params.get("question", "Please respond:")
            timeout = int(params.get("timeout", "300"))

            if self.status_dir:
                set_pending_user_input(self.status_dir, question, timeout)

            return {
                "success": True,
                "content": f"Question sent to user: {question}",
                "error": "",
                "file_paths": [],
                "summary": f"User input requested: {question[:100]}",
            }
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "error": str(e),
                "file_paths": [],
                "summary": "Failed to request user input",
            }


# Legacy function wrapper
def request_user_input(question: str, timeout: str = "300", **kwargs) -> str:
    """Legacy wrapper for RequestUserInputTool."""
    tool = RequestUserInputTool(
        root_dir=kwargs.get("root_dir", ""),
        status_dir=kwargs.get("status_dir", ""),
    )
    result = tool.execute({"question": question, "timeout": timeout})
    return result.get("content", "") if result.get("success") else f"Error: {result.get('error', '')}"


__all__ = ["create_tool", "list_tools", "get_tool", "request_user_input"]
