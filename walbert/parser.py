import re
from typing import List, Dict, Any

class BlockParser:
    @staticmethod
    def parse(text: str) -> List[Dict[str, str]]:
        blocks = []
        block_pattern = r'\[walbert_([a-z_]+)_start\](.*?)\[walbert_\1_end\]'
        for match in re.finditer(block_pattern, text, re.DOTALL):
            block_type = match.group(1)
            block_content = match.group(2).strip()

            # Remove triple backticks and optional language specifier
            block_content = re.sub(r'^```\w*\s*|```\s*$', '', block_content, flags=re.MULTILINE)

            blocks.append({"type": block_type, "content": block_content.strip()})
        return blocks