"""
Configuration classes for Walbert
"""

from dataclasses import dataclass
from typing import Dict

from walbert.model_config import ModelConfig

from typing import Dict, Optional
@dataclass
class Config:
    """System configuration"""
    model_configs: Dict[str, ModelConfig]
    llama_binary_path: str
    mmproj_path: str = ""
    log_level: str = "DEBUG"
    server_port: int = 8080
    server_health_check_timeout: int = 2
    server_startup_timeout: int = 60
    python_execution_timeout: int = 60
    bash_execution_timeout: int = 60
    autonomous_operation_timeout: int = 120
    conversation_log_dir: str = "instance/conversations"
    temp_dir_prefix: str = "walbert_python_"
    walbert_port: int = 8081
    udp_port: int = 9999
    be_presbyterian: bool = True
    peer_communication_enabled: bool = False
    python_execution_enabled: bool = False
    bash_execution_enabled: bool = False
    audio_enabled: bool = False
    stt_enabled: bool = False
    tts_enabled: bool = False
    bluetooth_device: Optional[str] = None
    stt_timeout: int = 30
    user_input_timeout: int = 60
    tts_voice: str = "default"