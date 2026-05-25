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

        i = 0
        while i < len(response_text):
            found_block = None
            for block in self.block_starts:
                if response_text.startswith(block, i):
                    found_block = block
                    break

            if found_block:
                if current_block:
                    parsed[current_block] = ''.join(current_content).strip()
                current_block = self.block_mapping[found_block]
                current_content = []
                i += len(found_block)
            elif current_block:
                current_content.append(response_text[i])
                i += 1
            else:
                i += 1

        if current_block and current_content:
            parsed[current_block] = ''.join(current_content).strip()

        return parsed
