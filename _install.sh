#!/bin/bash
# Walbert Installation Script

set -e

echo "Setting up Walbert..."

sudo apt install -y build-essential libssl-dev zlib1g-dev \
                 libbz2-dev libreadline-dev libsqlite3-dev \
                 libffi-dev liblzma-dev libudev-dev
sudo apt install -y python3-dev
sudo apt install -y portaudio19-dev
sudo apt install -y libbluetooth-dev

# Create directories
mkdir -p instance
mkdir -p instance/conversations
mkdir -p instance/llama.cpp
mkdir -p instance/llama.cpp/bin
mkdir -p instance/models

echo "Creating Python virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment"
    exit 1
fi

echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

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
    MODEL_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q4_K_M-mmproj-BF16.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "Downloading $MODEL_PATH..."
        wget --content-disposition "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-Q4_K_M.gguf?download=true" -O "$MODEL_PATH"
    else
        echo "$MODEL_PATH already exists, skipping download."
    fi
    if [ ! -f "$MMPROJ_PATH" ]; then
        echo "Downloading $MMPROJ_PATH..."
        wget --content-disposition "https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/main/Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf?download=true" -O "$MMPROJ_PATH"
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

echo "Configure Bluetooth Audio Device:"
read -p "Enable Bluetooth audio routing? (y/n) [n]: " bt_choice
bt_enabled=${bt_choice:-n}
BT_DEVICE="null"
BT_SINK="null"
BT_SOURCE="null"

if [[ "$bt_enabled" == "y" ]]; then
    if command -v bluetoothctl &> /dev/null; then
        echo "Scanning for Bluetooth audio devices (10 seconds)..."
        bluetoothctl --timeout 10 scan on

        echo "Discovered devices:"
        bluetoothctl devices

        device_count=$(bluetoothctl devices | grep -c "Device" || echo "0")

        if [ "$device_count" -gt 0 ]; then
            echo "Select a device by number (1-$device_count):"
            read -p "Enter choice: " device_num

            if [ "$device_num" -ge 1 ] && [ "$device_num" -le "$device_count" ]; then
                BT_MAC=$(bluetoothctl devices | grep "Device" | sed -n "${device_num}p" | awk '{print $2}')
                echo "Pairing and connecting to $BT_MAC..."

                echo -e "pair $BT_MAC\ntrust $BT_MAC" | bluetoothctl

                echo "Connecting (attempt 1)..."
                echo -e "connect $BT_MAC" | bluetoothctl
                sleep 1
                echo "Connecting (attempt 2)..."
                echo -e "connect $BT_MAC" | bluetoothctl

                echo "Bluetooth device info:"
                echo -e "info $BT_MAC" | bluetoothctl

                BT_DEVICE="$BT_MAC"

                # Try to switch card profile to headset (HFP/HSP) to expose microphone
                CARD_NAME=$(pactl list cards short | grep -i "${BT_MAC//:/}" | awk '{print $2}' || echo "")
                if [ -n "$CARD_NAME" ]; then
                    echo "Detected Bluetooth card: $CARD_NAME"
                    echo "Setting profile to headset_head_unit (if available)..."
                    pactl set-card-profile "$CARD_NAME" headset_head_unit || true
                    pactl set-card-profile "$CARD_NAME" handsfree_head_unit || true
                fi

                # Detect Bluetooth sink and source names
                BT_SINK=$(pactl list short sinks | grep -i "${BT_MAC//:/}" | awk '{print $2}' | head -n1 || echo "null")
                BT_SOURCE=$(pactl list short sources | grep -i "${BT_MAC//:/}" | awk '{print $2}' | head -n1 || echo "null")

                echo "Detected Bluetooth sink: $BT_SINK"
                echo "Detected Bluetooth source: $BT_SOURCE"
            else
                echo "Invalid selection. Using null."
                BT_DEVICE="null"
            fi
        else
            echo "No devices found."
            BT_DEVICE="null"
        fi
    else
        echo "bluetoothctl not found. Please configure manually in config.json."
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
    "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-ubuntu-x64.tar.gz"

    echo "Extracting llama.cpp binary..."
    tar -xzf llama.cpp.tar.gz -C instance/llama.cpp/bin --strip-components=1
    rm llama.cpp.tar.gz
else
    echo "llama.cpp already exists, skipping download."
fi

echo "Installation complete"
echo "Please edit instance/config.json with your specific paths before running Walbert"

chmod +x _run.sh
