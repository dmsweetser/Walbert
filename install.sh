#!/bin/bash
# Walbert installation script
# Creates virtual environment, installs dependencies, and downloads required files

set -e

mkdir -p instance
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin

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

# Create default config file
cat > instance/config.json << 'EOL'
{
    "model_configs": {
        "ministral": {
            "model_path": "instance/models/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf",
            "context_size": 125000,
            "output_tokens": 125000,
            "temperature": 0.15,
            "top_p": 1.0,
            "top_k": 20,
            "min_p": 0.01
        },
        "devstral": {
            "model_path": "instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
            "context_size": 125000,
            "output_tokens": 62500,
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0
        }
    },
    "llama_binary_path": "instance/llama.cpp/bin/llama-server",
    "mmproj_path": "instance/models/Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf",
    "log_level": "INFO"
}
EOL

# Create default I/O config file
if [ ! -f "instance/io_config.json" ]; then
    cat > instance/io_config.json << 'EOL'
{
    "io_layers": {
        "console": {
            "enabled": true,
            "require_authorization": false
        },
        "serial": {
            "enabled": false,
            "require_authorization": true,
            "port": null,
            "baudrate": 9600
        },
        "bluetooth": {
            "enabled": false,
            "require_authorization": true,
            "port": "/dev/rfcomm0",
            "baudrate": 9600
        },
        "usb": {
            "enabled": false,
            "require_authorization": true
        },
        "python_code": {
            "enabled": false,
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

# Ministral-14B model
download_model "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf" "https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf?download=true"

# Ministral-14B mmproj
download_model "Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf" "https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf?download=true"

# Devstral-24B model
download_model "Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf" "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true"

# Download llama.cpp binary
echo "Downloading llama.cpp binary..."
wget -O llama.cpp.tar.gz \
    "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-ubuntu-x64.tar.gz"
if [ $? -ne 0 ]; then
    echo "Error: Failed to download llama.cpp binary"
    exit 1
fi

# Extract binary
echo "Extracting llama.cpp binary..."
tar -xzf llama.cpp.tar.gz -C instance/llama.cpp/bin --strip-components=1
rm llama.cpp.tar.gz
if [ $? -ne 0 ]; then
    echo "Error: Failed to extract llama.cpp binary"
    exit 1
fi

echo "Installation complete."