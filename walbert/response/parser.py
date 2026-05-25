"""
Response parser implementation
"""

import re
from typing import Dict

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_patterns = {
            "response": r"~walbert_response_start~\s*(.*?)\s*~walbert_response_end~",
            "channel": r"~walbert_response_channel_start~\s*(.*?)\s*~walbert_response_channel_end~",
            "should_query_datastore": r"~walbert_should_query_datastore_start~\s*(.*?)\s*~walbert_should_query_datastore_end~",
            "conversation_complete": r"~walbert_conversation_complete_start~\s*(.*?)\s*~walbert_conversation_complete_end~",
            "sql_execute": r"~walbert_sql_execute_start~\s*(.*?)\s*~walbert_sql_execute_end~",
            "skill_execute": r"~walbert_skill_execute_start~\s*(.*?)\s*~walbert_skill_execute_end~"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        parsed = {}

        for key, pattern in self.block_patterns.items():
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                parsed[key] = match.group(1).strip()

        return parsed
