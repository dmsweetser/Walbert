#!/bin/bash
# Walbert installation script
# Creates virtual environment, installs dependencies, and downloads required files

set -e

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi

# Download models and binaries
echo "Downloading models and binaries..."
chmod +x download_models.sh
./download_models.sh
if [ $? -ne 0 ]; then
    echo "Error: Failed to download models"
    exit 1
fi

# Create default configuration files
echo "Creating default configuration files..."
python3 -c "
import json

# Create default config.json
config = {
    'model_paths': {
        'primary': 'models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf',
        'mmproj': 'models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf',
        'devstral': 'models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf'
    },
    'llama_binary_path': 'llama.cpp/bin/llama-completion',
    'log_level': 'INFO'
}

with open('config.json', 'w') as f:
    json.dump(config, f, indent=4)

# Create default io_config.json
io_config = {
    'io_layers': {
        'console': {
            'enabled': True,
            'require_authorization': False
        },
        'serial': {
            'enabled': False,
            'require_authorization': True
        },
        'bluetooth': {
            'enabled': False,
            'require_authorization': True
        },
        'usb': {
            'enabled': False,
            'require_authorization': True
        },
        'python_code': {
            'enabled': True,
            'require_authorization': True
        }
    }
}

with open('io_config.json', 'w') as f:
    json.dump(io_config, f, indent=4)
"

echo "Installation completed successfully!"
