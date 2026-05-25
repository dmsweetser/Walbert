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
            "~walbert_conversation_complete_start~",
            "~walbert_sql_execute_start~",
            "~walbert_skill_execute_start~",
            "~walbert_input_channel_start~"
        ]
        self.block_mapping = {
            "~walbert_response_start~": "response",
            "~walbert_response_channel_start~": "channel",
            "~walbert_should_query_datastore_start~": "should_query_datastore",
            "~walbert_conversation_complete_start~": "conversation_complete",
            "~walbert_sql_execute_start~": "sql_execute",
            "~walbert_skill_execute_start~": "skill_execute",
            "~walbert_input_channel_start~": "input_channel"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        parsed = {}
        current_block = None
        current_content = []

        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if line in self.block_starts:
                if current_block:
                    parsed[current_block] = '\n'.join(current_content).strip()
                current_block = self.block_mapping[line]
                current_content = []
            elif current_block:
                current_content.append(line)

        if current_block and current_content:
            parsed[current_block] = '\n'.join(current_content).strip()

        return parsed
