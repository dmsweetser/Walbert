#!/bin/bash
# Walbert Android (Termux) Installation Script

set -e

echo "Setting up Walbert for Termux/Android..."

# Update and install dependencies
pkg update -y
pkg upgrade -y
pkg install -y python git clang make cmake wget tar

# Create directories
mkdir -p instance/{conversations,models,llama.cpp/bin}

# Set up Python virtual environment
echo "Creating Python virtual environment..."
python -m venv venv --system-site-packages
source venv/bin/activate

pip install --upgrade pip setuptools wheel
pip install -r requirements_android.txt

# Model selection
echo "Select a model:"
echo "1) Devstral-24B-Instruct-GGUF (Default)"
echo "2) Qwen3.6-35B-A3B"
echo "3) Ministral 3 - 8B"
echo "4) Ministral 3 - 3B"
read -p "Enter choice: " model_choice

# Set model paths and parameters based on choice
MODEL_PATH=""
MMPROJ_PATH=""
CONTEXT_SIZE=""
OUTPUT_TOKENS=""
TEMPERATURE=""
TOP_P=""
TOP_K=""
MIN_P=""

if [ "$model_choice" == "2" ]; then
    MODEL_PATH="instance/models/Qwen3.6-35B-A3B-UD-IQ3_S.gguf"
    MMPROJ_PATH="instance/models/Qwen3.6-35B-A3B-UD-IQ3_S-mmproj-BF16.gguf"
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.8
    TOP_K=20
    MIN_P=0.0
elif [ "$model_choice" == "3" ]; then
    MODEL_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf"
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.00
elif [ "$model_choice" == "4" ]; then
    MODEL_PATH="instance/models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH=""
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.00
else
    MODEL_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.05
fi

# Download model files if missing
if [ ! -f "$MODEL_PATH" ]; then
    echo "Downloading $MODEL_PATH..."
    wget --content-disposition \
      "https://huggingface.co/unsloth/${MODEL_PATH##*/}/resolve/main/${MODEL_PATH##*/}?download=true" \
      -O "$MODEL_PATH"
else
    echo "$MODEL_PATH already exists, skipping download."
fi

if [ -n "$MMPROJ_PATH" ] && [ ! -f "$MMPROJ_PATH" ]; then
    echo "Downloading $MMPROJ_PATH..."
    wget --content-disposition \
      "https://huggingface.co/unsloth/${MMPROJ_PATH##*/}/resolve/main/${MMPROJ_PATH##*/}?download=true" \
      -O "$MMPROJ_PATH"
else
    echo "$MMPROJ_PATH already exists or is not required, skipping download."
fi

# Download Piper TTS model
PIPER_MODEL="instance/models/en_GB-northern_english_male-medium.onnx"
if [ ! -f "$PIPER_MODEL" ]; then
    echo "Downloading Piper TTS model..."
    wget -O "$PIPER_MODEL" \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/GB/northern_english/male/medium/en_GB-northern_english_male-medium.onnx"
else
    echo "$PIPER_MODEL already exists, skipping download."
fi

# Write config.json
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
    "mmproj_path": "$MMPROJ_PATH",
    "piper_model": "$PIPER_MODEL",
    "audio_enabled": false,
    "stt_enabled": false,
    "tts_enabled": false,
    "bluetooth_device": "null",
    "bluetooth_sink": "null",
    "bluetooth_source": "null",
    "log_level": "DEBUG",
    "walbert_port": 8081,
    "udp_port": 9999,
    "be_presbyterian": true,
    "peer_communication_enabled": false,
    "python_execution_enabled": false,
    "bash_execution_enabled": false,
    "stt_timeout": 30,
    "user_input_timeout": 60,
    "tts_voice": "default",
    "database_path": "instance/walbert.db"
}
EOF

echo "Created config.json"

# Download llama.cpp binary (Android ARM64)
if [ ! -f "instance/llama.cpp/bin/llama-server" ]; then
    echo "Downloading llama.cpp..."
    wget -O llama.cpp.tar.gz \
      "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-android-arm64.tar.gz"

    echo "Extracting..."
    tar -xzf llama.cpp.tar.gz -C instance/llama.cpp/bin --strip-components=1
    rm llama.cpp.tar.gz
else
    echo "llama.cpp already exists, skipping download."
fi

echo "Installation complete."
chmod +x _run.sh