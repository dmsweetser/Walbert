"""
Configuration classes for Walbert
"""

from dataclasses import dataclass
from typing import Dict, Optional

from walbert.model_config import ModelConfig


@dataclass
class Config:
    """System configuration"""
    model_configs: Dict[str, ModelConfig]
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
    bluetooth_device: Optional[str] = None
    user_input_timeout: int = 60
    database_path: str = "instance/walbert.db"
    # llama-server binary path (for discovery)
    llama_binary_path: str = "llama-server"
    # AI-Builder patterns: context management
    max_context_tokens: int = 0  # 0 = unlimited, trim to this budget
    max_output_tokens: int = 0  # 0 = unlimited
    max_tool_result_length: int = 10000  # truncate tool results longer than this
    # AI-Builder patterns: LLM endpoint (env vars: WALBERT_ENDPOINT_URL, WALBERT_MODEL_NAME, WALBERT_API_KEY)
    custom_endpoint_url: str = ""
    custom_api_key: str = ""
    custom_model_name: str = ""
    custom_verify_ssl: bool = True
    timeout: int = 300  # seconds
