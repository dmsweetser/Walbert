"""
Configuration classes for Walbert
"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Config:
    """System configuration"""
    model_paths: Dict[str, str]
    llama_binary_path: str
    log_level: str

@dataclass
class IOConfig:
    """I/O layer configuration"""
    io_layers: Dict[str, Dict[str, Any]]
