#!/bin/bash

# Create instance directory
mkdir -p instance

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create default configuration files
if [ ! -f "instance/config.json" ]; then
    cat > instance/config.json <<EOL
{
    "model_paths": {
        "primary": "instance/models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        "mmproj": "instance/models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf",
        "devstral": "instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    },
    "llama_binary_path": "llama.cpp/bin/llama-server",
    "log_level": "INFO"
}
EOL
fi

if [ ! -f "instance/io_config.json" ]; then
    cat > instance/io_config.json <<EOL
{
    "io_layers": {
        "console": {
            "enabled": true,
            "require_authorization": false
        },
        "serial": {
            "enabled": false,
            "require_authorization": true
        },
        "bluetooth": {
            "enabled": false,
            "require_authorization": true
        },
        "usb": {
            "enabled": false,
            "require_authorization": true
        },
        "python_code": {
            "enabled": true,
            "require_authorization": true
        }
    }
}
EOL
fi

# Create models directory
mkdir -p instance/models

# Download models if they don't exist
download_model() {
    local model_name=$1
    local model_url=$2
    local model_path="instance/models/$model_name"

    if [ ! -f "$model_path" ]; then
        echo "Downloading $model_name..."
        wget -O "$model_path" "$model_url"
    else
        echo "$model_name already exists, skipping download."
    fi
}

# Ministral-3B model
download_model "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf" "https://example.com/models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf"

# Ministral-3B mmproj
download_model "Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf" "https://example.com/models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf"

# Devstral-24B model
download_model "Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf" "https://example.com/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"

echo "Installation complete."