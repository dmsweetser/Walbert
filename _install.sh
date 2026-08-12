#!/bin/bash
# Walbert Installation Script

set -e

echo "Setting up Walbert..."

sudo apt install build-essential libssl-dev zlib1g-dev \
                 libbz2-dev libreadline-dev libsqlite3-dev \
                 libffi-dev liblzma-dev libudev-dev
sudo apt install python3-dev
sudo apt install portaudio19-dev
sudo apt install libbluetooth-dev

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
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Model selection and configuration
echo "Select a model:"
echo "1) Devstral-24B-Instruct-GGUF (Default)"
echo "2) Qwen3.6-35B-A3B"
echo "3) Ministral 3 - 8B"
read -p "Enter choice: " model_choice

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
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition  "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-IQ3_S.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition  "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -O "$MMPROJ_PATH"
    else
        echo "$MMPROJ_PATH already exists, skipping download."
    fi
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.8
    TOP_K=20
    MIN_P=0.0
elif [ "$model_choice" == "3" ]; then
    MODEL_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q4_K_M-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition  "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition  "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf?download=true" -O "$MMPROJ_PATH"
    else
        echo "$MMPROJ_PATH already exists, skipping download."
    fi
    CONTEXT_SIZE=8192
    OUTPUT_TOKENS=4096
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.00
else
    MODEL_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition  "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition  "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -O "$MMPROJ_PATH"
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

# Configure Bluetooth Audio Device
echo "Configure Bluetooth Audio Device:"
read -p "Enable Bluetooth audio routing? (y/n) [n]: " bt_choice
bt_enabled=${bt_choice:-n}
BT_DEVICE="null"
if [[ "$bt_enabled" == "y" ]]; then
    echo "Scanning for Bluetooth audio devices..."
    if command -v bluetoothctl &> /dev/null; then
        echo "Starting Bluetooth scan..."
        timeout 10 bluetoothctl scan on
        sleep 5
        bluetoothctl scan off
        echo "Available devices:"
        bluetoothctl devices
        read -p "Enter MAC address of target device: " BT_MAC
        if [ -n "$BT_MAC" ]; then
            echo "Pairing with $BT_MAC..."
            bluetoothctl pair "$BT_MAC"
            echo "Connecting to $BT_MAC..."
            bluetoothctl connect "$BT_MAC"
            BT_DEVICE="$BT_MAC"
        else
            BT_DEVICE="null"
        fi
    else
        echo "bluetoothctl not found. Please configure manually in config.json."
        BT_DEVICE="null"
    fi
fi

# Configure optional features:
echo "Configure optional features:"
read -p "Enable STT (Whisper)? (y/n) [n]: " stt_choice
stt_enabled=${stt_choice:-n}
if [[ "$stt_enabled" == "y" ]]; then stt_enabled=true; else stt_enabled=false; fi

read -p "Enable TTS? (y/n) [n]: " tts_choice
tts_enabled=${tts_choice:-n}
if [[ "$tts_enabled" == "y" ]]; then tts_enabled=true; else tts_enabled=false; fi

# Generate config.json
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
    "llama_binary_path": "instance/llama.cpp/bin/llama-completion",
    "mmproj_path": "$MMPROJ_PATH",
    "log_level": "DEBUG",
    "server_port": 8080,
    "server_health_check_timeout": 2,
    "server_startup_timeout": 60,
    "python_execution_timeout": 30,
    "autonomous_operation_timeout": 120,
    "conversation_log_dir": "instance/conversations",
    "walbert_port": 8081,
    "udp_port": 9999,
    "be_presbyterian": true,
    "peer_communication_enabled": false,
    "python_execution_enabled": false,
    "bash_execution_enabled": false,
    "audio_enabled": false,
    "stt_enabled": $stt_enabled,
    "tts_enabled": $tts_enabled,
    "bluetooth_device": "$BT_DEVICE",
    "stt_timeout": 30,
    "user_input_timeout": 60,
    "tts_voice": "default"
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
chmod +x _run.sh
