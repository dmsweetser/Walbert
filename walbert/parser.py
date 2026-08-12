import re
from typing import List, Dict, Any

class BlockParser:
    @staticmethod
    def parse(text: str) -> List[Dict[str, str]]:
        blocks = []
        # Match start or end markers, with or without brackets, case-insensitive
        pattern = re.compile(r'\[?\bwalbert_([a-zA-Z_]+(?:_[a-zA-Z_]+)?)_(?:start|end)\]?', re.IGNORECASE)
        
        current_type = None
        current_content = ""
        last_end_pos = 0
        
        for match in pattern.finditer(text):
            start_pos = match.start()
            end_pos = match.end()
            
            # Append any text between the last marker and this one to current content
            if current_type is not None:
                current_content += text[last_end_pos:start_pos]
            
            marker_text = match.group(0).lower()
            block_type = match.group(1)
            is_start = "start" in marker_text
            
            if is_start:
                # If there's an open block, close it (push to blocks)
                if current_type is not None:
                    blocks.append({"type": current_type, "content": current_content.strip()})
                    current_content = ""
                current_type = block_type
            else: # end
                if current_type is not None:
                    # Close the block
                    blocks.append({"type": current_type, "content": current_content.strip()})
                    current_type = None
                    current_content = ""
                else:
                    # End block without start block: start a new block from here
                    current_type = block_type
                    current_content = ""
            
            last_end_pos = end_pos
            
        # Handle remaining text if a block is open
        if current_type is not None:
            current_content += text[last_end_pos:]
            blocks.append({"type": current_type, "content": current_content.strip()})
            
        # Clean up triple backticks from each block's content
        cleaned_blocks = []
        for block in blocks:
            content = block["content"]
            content = re.sub(r'^```\w*\s*|```\s*$', '', content, flags=re.MULTILINE).strip()
            cleaned_blocks.append({"type": block["type"], "content": content})
            
        return cleaned_blocks