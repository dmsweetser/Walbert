#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import sys
import os
import logging
import json
from walbert import Config, IOConfig, WalbertAgent
from walbert.config import ModelConfig

# Initialize logging
os.makedirs('instance', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instance/walbert.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('walbert')

def load_config() -> Config:
    """Load system configuration"""
    try:
        with open('instance/config.json', 'r') as f:
            config_data = json.load(f)
            model_configs = {
                'ministral': ModelConfig(
                    model_path=config_data['model_configs']['ministral']['model_path'],
                    context_size=config_data['model_configs']['ministral']['context_size'],
                    output_tokens=config_data['model_configs']['ministral']['output_tokens'],
                    temperature=config_data['model_configs']['ministral']['temperature'],
                    top_p=config_data['model_configs']['ministral']['top_p'],
                    top_k=config_data['model_configs']['ministral']['top_k'],
                    min_p=config_data['model_configs']['ministral']['min_p']
                ),
                'devstral': ModelConfig(
                    model_path=config_data['model_configs']['devstral']['model_path'],
                    context_size=config_data['model_configs']['devstral']['context_size'],
                    output_tokens=config_data['model_configs']['devstral']['output_tokens'],
                    temperature=config_data['model_configs']['devstral']['temperature'],
                    top_p=config_data['model_configs']['devstral']['top_p'],
                    top_k=config_data['model_configs']['devstral']['top_k'],
                    min_p=config_data['model_configs']['devstral']['min_p']
                )
            }
            return Config(
                model_configs=model_configs,
                llama_binary_path=config_data['llama_binary_path'],
                mmproj_path=config_data.get('mmproj_path', ""),
                log_level=config_data.get('log_level', "INFO")
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def load_io_config() -> IOConfig:
    """Load I/O configuration"""
    try:
        with open('instance/io_config.json', 'r') as f:
            io_config_data = json.load(f)
            return IOConfig(io_config_data)
    except FileNotFoundError:
        logger.error("instance/io_config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading I/O config: {e}")
        sys.exit(1)

def main():
    """Main entry point"""
    config = load_config()
    io_config = load_io_config()

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    agent = WalbertAgent(config, io_config)
    agent.run()

if __name__ == "__main__":
    main()
