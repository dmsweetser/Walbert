"""
Response parser implementation
"""

import re
from typing import Dict

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_starts = [
            "~walbert_response_start~",
            "~walbert_response_channel_start~",
            "~walbert_should_query_datastore_start~",
            "~walbert_should_consult_smarter_cousin_start~",
            "~walbert_conversation_complete_start~",
            "~walbert_sql_execute_start~",
            "~walbert_skill_execute_start~",
            "~walbert_input_channel_start~"
        ]
        self.block_mapping = {
            "~walbert_response_start~": "response",
            "~walbert_response_channel_start~": "channel",
            "~walbert_should_query_datastore_start~": "should_query_datastore",
            "~walbert_should_consult_smarter_cousin_start~": "should_consult_smarter_cousin",
            "~walbert_conversation_complete_start~": "conversation_complete",
            "~walbert_sql_execute_start~": "sql_execute",
            "~walbert_skill_execute_start~": "skill_execute",
            "~walbert_input_channel_start~": "input_channel"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        if not response_text:
            return {}

        parsed = {}
        for block in self.block_starts:
            # Try to find the block with proper handling of newlines
            pattern = re.escape(block) + r"(.*?)(?=(~walbert_|$))"
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                content = match.group(1).strip()
                parsed[self.block_mapping[block]] = content
        return parsed
