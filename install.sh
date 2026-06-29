#!/bin/bash
# Walbert Installation Script

set -e

echo "Setting up Walbert..."

# Create directories
mkdir -p instance
mkdir -p instance/conversations
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin
mkdir -p instance/models

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

# Model selection and configuration
echo "Select a model:"
echo "1) Devstral-24B-Instruct-GGUF (Default)"
echo "2) Qwen3.6-35B-A3B"
read -p "Enter choice (1 or 2): " model_choice

MODEL_PATH=""
MMPROJ_PATH=""
CONTEXT_SIZE=""
OUTPUT_TOKENS=""
TEMPERATURE=""
TOP_P=""
TOP_K=""
MIN_P=""

if [ "$model_choice" == "2" ]; then
    MODEL_PATH="instance/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Qwen3.6-35B-A3B-UD-Q4_K_M-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        curl -L "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf?download=true" -o "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        curl -L "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -o "$MMPROJ_PATH"
    else
        echo "$MMPROJ_PATH already exists, skipping download."
    fi
    CONTEXT_SIZE=262144
    OUTPUT_TOKENS=131072
    TEMPERATURE=0.7
    TOP_P=0.8
    TOP_K=20
    MIN_P=0.0
else
    MODEL_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        curl -L "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true" -o "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        curl -L "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -o "$MMPROJ_PATH"
    else
        echo "$MMPROJ_PATH already exists, skipping download."
    fi
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.05
fi

# Generate config.json with selected model hyperparameters
cat > instance/config.json << EOF
{
    "model_configs": {
        "model": {
            "model_path": "$MODEL_PATH",
            "context_size": $CONTEXT_SIZE,
            "output_tokens": $OUTPUT_TOKENS,
            "temperature": $TEMPERATURE,
            "top_p": $TOP_P,
            "top_k": $TOP_K,
            "min_p": $MIN_P
        }
    },
    "llama_binary_path": "instance/llama.cpp/bin/llama-server",
    "mmproj_path": "$MMPROJ_PATH",
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
EOF

echo "Created default config at instance/config.json"
echo "Please edit this file with your specific paths and settings"

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
