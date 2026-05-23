"""
Response parser implementation
"""

import re
import json
from typing import Dict

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_patterns = {
            "response": r"~walbert_response_start~\s*(.*?)\s*~walbert_response_end~",
            "channel": r"~walbert_response_channel_start~\s*(.*?)\s*~walbert_response_channel_end~",
            "should_call_smarter_cousin": r"~walbert_should_call_smarter_cousin_start~\s*(.*?)\s*~walbert_should_call_smarter_cousin_end~",
            "should_query_datastore": r"~walbert_should_query_datastore_start~\s*(.*?)\s*~walbert_should_query_datastore_end~",
            "should_execute_skill": r"~walbert_should_execute_skill_start~\s*(.*?)\s*~walbert_should_execute_skill_end~",
            "should_store_memory": r"~walbert_should_store_memory_start~\s*(.*?)\s*~walbert_should_store_memory_end~",
            "conversation_complete": r"~walbert_conversation_complete_start~\s*(.*?)\s*~walbert_conversation_complete_end~",
            "db_command": r"~walbert_db_command_start~\s*(.*?)\s*(.*?)\s*~walbert_db_command_end~",
            "skill_execution": r"~walbert_skill_execution_start~\s*(.*?)\s*(.*?)\s*~walbert_skill_execution_end~",
            "memory_storage": r"~walbert_memory_storage_start~\s*(.*?)\s*~walbert_memory_storage_end~",
            "hardware_action": r"~walbert_hardware_action_start~\s*(.*?)\s*~walbert_hardware_action_end~"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        parsed = {}

        # Check for conversation complete first
        conv_complete_match = re.search(self.block_patterns["conversation_complete"], response_text, re.DOTALL)
        if conv_complete_match:
            parsed["conversation_complete"] = conv_complete_match.group(1).strip()

        # Parse all other blocks
        for key, pattern in self.block_patterns.items():
            if key == "conversation_complete":
                continue

            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                if key in ["db_command", "skill_execution"]:
                    try:
                        args = json.loads(match.group(2).strip()) if match.group(2).strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                    parsed[key] = {
                        "command": match.group(1).strip(),
                        "args": args
                    }
                elif key in ["memory_storage", "hardware_action"]:
                    try:
                        args = json.loads(match.group(1).strip()) if match.group(1).strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                    parsed[key] = args
                else:
                    parsed[key] = match.group(1).strip()

        return parsed
