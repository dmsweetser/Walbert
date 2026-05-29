"""
Configuration classes for Walbert
"""

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

@dataclass
class Config:
    """System configuration"""
    model_configs: Dict[str, ModelConfig]
    llama_binary_path: str
    mmproj_path: str = ""
    log_level: str = "INFO"
