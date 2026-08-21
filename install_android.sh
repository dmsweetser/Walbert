#!/bin/bash
# Walbert Android (Termux) Installation Script

set -e

echo "Setting up Walbert for Termux/Android..."

# Update and install base dependencies (Termux uses clang, not gcc)
pkg update -y
pkg upgrade -y
pkg install -y python git clang make cmake ffmpeg libsndfile portaudio

# Create project directories
mkdir -p instance
mkdir -p instance/conversations
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin
mkdir -p instance/models

# Create virtual environment
echo "Creating Python virtual environment..."
python -m venv venv --system-site-packages
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

# Install Python requirements (avoid forcing source builds to dodge gcc/clang issues)
pip install --upgrade pip
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
        wget --content-disposition "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-IQ3_S.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -O "$MMPROJ_PATH"
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
    MODEL_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q2_K.gguf"
    MMPROJ_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q2_K-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-Q2_K.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf?download=true" -O "$MMPROJ_PATH"
    else
        echo "$MMPROJ_PATH already exists, skipping download."
    fi
    CONTEXT_SIZE=4096
    OUTPUT_TOKENS=2048
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.00
else
    MODEL_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true" -O "$MMPROJ_PATH"
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

# Configure Bluetooth Audio Device (Termux)
echo "Configure Bluetooth Audio Device:"
read -p "Enable Bluetooth audio routing? (y/n) [n]: " bt_choice
bt_enabled=${bt_choice:-n}
BT_DEVICE="null"
BT_SINK="null"
BT_SOURCE="null"

if [[ "$bt_enabled" == "y" ]]; then
    if command -v termux-bluetooth &> /dev/null; then
        echo "Scanning for Bluetooth audio devices..."
        termux-bluetooth scan on
        sleep 5
        termux-bluetooth scan off

        echo "Available devices:"
        termux-bluetooth list

        device_count=$(termux-bluetooth list | grep -c "Address:" || echo "0")

        if [ "$device_count" -gt 0 ]; then
            echo "Select a device by number (1-$device_count):"
            read -p "Enter choice: " device_num

            if [ "$device_num" -ge 1 ] && [ "$device_num" -le "$device_count" ]; then
                BT_MAC=$(termux-bluetooth list | grep "Address:" | sed -n "${device_num}p" | awk -F'[ ,]' '{print $2}')
                echo "Pairing with $BT_MAC..."
                termux-bluetooth pair "$BT_MAC"
                echo "Connecting to $BT_MAC..."
                termux-bluetooth connect "$BT_MAC"
                BT_DEVICE="$BT_MAC"
            else
                echo "Invalid selection. Using null."
                BT_DEVICE="null"
            fi
        else
            echo "No devices found."
            BT_DEVICE="null"
        fi
    else
        echo "termux-bluetooth not found. Please configure manually in config.json."
        BT_DEVICE="null"
    fi
fi

if [[ "$bt_enabled" == "y" ]]; then bt_enabled=true; else bt_enabled=false; fi

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
    "audio_enabled": $bt_enabled,
    "stt_enabled": $bt_enabled,
    "tts_enabled": $bt_enabled,
    "bluetooth_device": "$BT_DEVICE",
    "bluetooth_sink": "$BT_SINK",
    "bluetooth_source": "$BT_SOURCE",
    "stt_timeout": 30,
    "user_input_timeout": 60,
    "tts_voice": "default",
    "database_path": "instance/walbert.db"
}
EOF

echo "Created default config at instance/config.json"
echo "Please edit this file with your specific paths and settings"

echo "Downloading llama.cpp binary..."
if [ ! -f "instance/llama.cpp/bin/llama-server" ]; then
    wget -O llama.cpp.tar.gz \
    "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-android-arm64.tar.gz"

    echo "Extracting llama.cpp binary..."
    tar -xzf llama.cpp.tar.gz -C instance/llama.cpp/bin --strip-components=1
    rm llama.cpp.tar.gz
else
    echo "llama.cpp already exists, skipping download."
fi

echo "Installation complete"
echo "Please edit instance/config.json with your specific paths before running Walbert"

chmod +x _run.sh
