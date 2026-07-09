import re
from typing import List, Dict, Any

class BlockParser:
    @staticmethod
    def parse(text: str) -> List[Dict[str, str]]:
        blocks = []
        block_pattern = r'\[walbert_([a-z_]+)_start\](.*?)\[/walbert_\1_end\]'
        for match in re.finditer(block_pattern, text, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()
            blocks.append({"type": block_type, "content": block_content})
        return blocks