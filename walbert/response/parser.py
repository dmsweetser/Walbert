"""
Response parser implementation
"""

import re
from typing import Dict

class ResponseParser:
    """Parses Walbert's response blocks"""
    def __init__(self):
        self.block_patterns = {
            "conversation_complete": r"~walbert_conversation_complete~\n(.*?)\n~walbert_conversation_complete~",
            "sql_execute": r"~walbert_sql_execute~\n(.*?)\n~walbert_sql_execute~",
            "skill_execute": r"~walbert_skill_execute~\n(.*?)\n~walbert_skill_execute~",
            "input_channel": r"~walbert_input_channel_start~\n(.*?)\n~walbert_input_channel_end~"
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

        # Parse channel-specific responses
        channel_pattern = r"~(.*?)_response~\n(.*?)\n~.*?_response~"
        channel_matches = re.findall(channel_pattern, response_text, re.DOTALL)
        for channel, content in channel_matches:
            parsed[f"{channel}_response"] = content.strip()

        return parsed
