#!/bin/bash
# Walbert installation script
# Creates virtual environment, installs dependencies, and downloads required files

set -e

mkdir -p instance
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin
mkdir -p instance/models

echo "Select a model to install:"
echo "1) Devstral 24B"
echo "2) Ministral 3B"
echo "3) Ministral 8B"
echo "4) Ministral 14B"
read -p "Enter choice [1-4]: " model_choice

case $model_choice in
    1)
        MODEL_NAME="Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
        MODEL_URL="https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true"
        ;;
    2)
        MODEL_NAME="Ministral-3-3B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf"
        MODEL_URL="https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf?download=true"
        ;;
    3)
        MODEL_NAME="Ministral-3-8B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf"
        MODEL_URL="https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf?download=true"
        ;;
    4)
        MODEL_NAME="Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf"
        MODEL_URL="https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf?download=true"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo "You selected: $MODEL_NAME"

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

# Create config.json dynamically
cat > instance/config.json << EOL
{
    "model_configs": {
        "model": {
            "model_path": "instance/models/$MODEL_NAME",
            "context_size": 32768,
            "output_tokens": 16384,
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0
        }
    },
    "llama_binary_path": "instance/llama.cpp/bin/llama-server",
    "mmproj_path": "instance/models/$MMPROJ_NAME",
    "log_level": "DEBUG"
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
        }
    }
}
EOL
fi

# Download models if missing
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

download_model "$MODEL_NAME" "$MODEL_URL"
download_model "$MMPROJ_NAME" "$MMPROJ_URL"

# Download llama.cpp binary
echo "Downloading llama.cpp binary..."
if [ ! -f "instance/llama.cpp/bin/llama-server" ]; then
    wget -O llama.cpp.tar.gz \
    "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-ubuntu-x64.tar.gz"

    echo "Extracting llama.cpp binary..."
    tar -xzf llama.cpp.tar.gz -C instance/llama.cpp/bin --strip-components=1
    rm llama.cpp.tar.gz
else
    echo "llama.cpp already exists, skipping download."
fi

echo "Installation complete."
