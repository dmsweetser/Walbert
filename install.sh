#!/bin/bash
# Walbert installation script

# Create directories
mkdir -p instance
mkdir -p instance/conversations
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin
mkdir -p instance/models

echo "Select a model to install:"
echo "1) Devstral 24B"
echo "2) Ministral 14B"
echo "3) Mistral 7B"
echo "4) Gemma 4 12B"
read -p "Enter choice: " model_choice

case $model_choice in
    1)
        MODEL_NAME="Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
        MODEL_URL="https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true"
        ;;
    2)
        MODEL_NAME="Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
        MMPROJ_NAME="Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf"
        MODEL_URL="https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF/resolve/main/Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf?download=true"
        ;;
    3)
        MODEL_NAME="Mistral-7B-Instruct-v0.3.IQ4_XS.gguf"
        MMPROJ_NAME=""
        MODEL_URL="https://huggingface.co/MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3.IQ4_XS.gguf?download=true"
        MMPROJ_URL=""
        ;;
    4)
        MODEL_NAME="gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
        MMPROJ_NAME="gemma-4-12B-it-qat-UD-Q4_K_XL-mmproj-F32.gguf"
        MODEL_URL="https://huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF/resolve/main/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf?download=true"
        MMPROJ_URL="https://huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF/resolve/main/mmproj-F32.gguf?download=true"
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

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi

# Create default config if it doesn't exist
if [ ! -f "instance/config.json" ]; then
    cat > instance/config.json <<EOL
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
    "log_level": "DEBUG",
    "server_port": 8080,
    "server_health_check_timeout": 2,
    "server_startup_timeout": 60,
    "python_execution_timeout": 30,
    "autonomous_operation_timeout": 120,
    "conversation_log_dir": "instance/conversations",
    "database_path": "instance/walbert.db",
    "be_presbyterian": true
}
EOL
    echo "Created default config at instance/config.json"
    echo "Please edit this file with your specific paths and settings"
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

echo "Installation complete"
echo "Please edit instance/config.json with your specific paths before running Walbert"

# Make run script executable
chmod +x run.sh
