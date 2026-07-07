from dataclasses import dataclass
from typing import Dict

@dataclass
class ModelConfig:
    """Model-specific configuration"""
    model_path: str
    context_size: int
    output_tokens: int
    temperature: float
    top_p: float
    top_k: int
    min_p: float