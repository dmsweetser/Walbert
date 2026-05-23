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
            "response": r"~walbert_response_start~\n(.*?)\n~walbert_response_end~",
            "channel": r"~walbert_response_channel_start~\n(.*?)\n~walbert_response_channel_end~",
            "should_call_smarter_cousin": r"~walbert_should_call_smarter_cousin_start~\n(.*?)\n~walbert_should_call_smarter_cousin_end~",
            "should_query_datastore": r"~walbert_should_query_datastore_start~\n(.*?)\n~walbert_should_query_datastore_end~",
            "should_execute_skill": r"~walbert_should_execute_skill_start~\n(.*?)\n~walbert_should_execute_skill_end~",
            "should_store_memory": r"~walbert_should_store_memory_start~\n(.*?)\n~walbert_should_store_memory_end~",
            "conversation_complete": r"~walbert_conversation_complete_start~\n(.*?)\n~walbert_conversation_complete_end~",
            "db_command": r"~walbert_db_command_start~\n(.*?)\n(.*?)\n~walbert_db_command_end~",
            "skill_execution": r"~walbert_skill_execution_start~\n(.*?)\n(.*?)\n~walbert_skill_execution_end~",
            "memory_storage": r"~walbert_memory_storage_start~\n(.*?)\n(.*?)\n~walbert_memory_storage_end~",
            "hardware_action": r"~walbert_hardware_action_start~\n(.*?)\n~walbert_hardware_action_end~"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        parsed = {}
        for key, pattern in self.block_patterns.items():
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                if key in ["db_command", "skill_execution", "memory_storage", "hardware_action"]:
                    try:
                        args = json.loads(match.group(2).strip()) if match.group(2).strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                    parsed[key] = {
                        "command": match.group(1).strip(),
                        "args": args
                    }
                else:
                    parsed[key] = match.group(1).strip()
        return parsed
