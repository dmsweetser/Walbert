"""
Response parser implementation
"""

import re
from typing import Dict

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_patterns = {
            "response": r"~walbert_response~\n(.*?)\n~walbert_response~",
            "channel": r"~walbert_response_channel~\n(.*?)\n~walbert_response_channel~",
            "should_query_datastore": r"~walbert_should_query_datastore~\n(.*?)\n~walbert_should_query_datastore~",
            "conversation_complete": r"~walbert_conversation_complete~\n(.*?)\n~walbert_conversation_complete~",
            "sql_execute": r"~walbert_sql_execute~\n(.*?)\n~walbert_sql_execute~",
            "skill_execute": r"~walbert_skill_execute~\n(.*?)\n~walbert_skill_execute~",
            "input_channel": r"~walbert_input_channel_start~\n(.*?)\n~walbert_input_channel_start~"
        }

    def parse_response(self, response_text: str) -> Dict:
        """Parse response text into structured data"""
        if not response_text:
            return {}

        parsed = {}
        for key, pattern in self.block_patterns.items():
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                parsed[key] = match.group(1).strip()
        return parsed
