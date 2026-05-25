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
            "~walbert_input_channel_start~"
        ]
        self.block_mapping = {
            "~walbert_response_start~": "response",
            "~walbert_response_channel_start~": "channel",
            "~walbert_should_query_datastore_start~": "should_query_datastore",
            "~walbert_conversation_complete_start~": "conversation_complete",
            "~walbert_sql_execute_start~": "sql_execute",
            "~walbert_input_channel_start~": "input_channel"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        parsed = {}
        for block in self.block_starts:
            if block in response_text:
                start_idx = response_text.find(block) + len(block)
                end_idx = len(response_text)
                for other_block in self.block_starts:
                    if other_block in response_text[start_idx:]:
                        other_idx = response_text.find(other_block, start_idx)
                        if other_idx < end_idx:
                            end_idx = other_idx
                content = response_text[start_idx:end_idx].strip()
                parsed[self.block_mapping[block]] = content
        return parsed
