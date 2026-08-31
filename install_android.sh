#!/bin/bash
# Walbert Android (Termux) Installation Script

set -e

echo "Setting up Walbert for Termux/Android..."

# Base dependencies
pkg update -y
pkg upgrade -y
pkg install -y python git clang make cmake ffmpeg libsndfile portaudio wget tar

pkg install build-essential python python-pip libpulse pulseaudio

curl -LO https://its-pointless.github.io/setup-pointless-repo.sh
bash setup-pointless-repo.sh
pkg install portaudio portaudio-dev

# Project directories
mkdir -p instance/{conversations,models,llama.cpp/bin}

# Virtual environment
echo "Creating Python virtual environment..."
python -m venv venv --system-site-packages

echo "Activating virtual environment..."
source venv/bin/activate

pip install --upgrade pip setuptools wheel

sed -i '/openai-whisper/d' requirements.txt

pip install pyaudio --global-option='build_ext' --global-option='-I$PREFIX/include' --global-option='-L$PREFIX/lib'

pip install -r requirements.txt

# Model selection
echo "Select a model:"
echo "1) Devstral-24B-Instruct-GGUF (Default)"
echo "2) Qwen3.6-35B-A3B"
echo "3) Ministral 3 - 8B"
read -p "Enter choice: " model_choice

case "$model_choice" in
  2)
    MODEL_PATH="instance/models/Qwen3.6-35B-A3B-UD-IQ3_S.gguf"
    MMPROJ_PATH="instance/models/Qwen3.6-35B-A3B-UD-IQ3_S-mmproj-BF16.gguf"
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.8
    TOP_K=20
    MIN_P=0.0
    ;;
  3)
    MODEL_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q2_K.gguf"
    MMPROJ_PATH="instance/models/Ministral-3-8B-Instruct-2512-Q2_K-mmproj-BF16.gguf"
    CONTEXT_SIZE=4096
    OUTPUT_TOKENS=2048
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.00
    ;;
  *)
    MODEL_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
    MMPROJ_PATH="instance/models/Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf"
    CONTEXT_SIZE=32768
    OUTPUT_TOKENS=16384
    TEMPERATURE=0.7
    TOP_P=0.9
    TOP_K=40
    MIN_P=0.05
    ;;
esac

# Download model files if missing
if [ ! -f "$MODEL_PATH" ]; then
    echo "Downloading model..."
    wget --content-disposition -O "$MODEL_PATH" \
      "$(grep -o 'https://.*\.gguf' <<< "$MODEL_PATH")"
fi

if [ ! -f "$MMPROJ_PATH" ]; then
    echo "Downloading mmproj..."
    wget --content-disposition -O "$MMPROJ_PATH" \
      "$(grep -o 'https://.*\.gguf' <<< "$MMPROJ_PATH")"
fi

# Download Piper TTS model
PIPER_MODEL="instance/models/en_GB-northern_english_male-medium.onnx"
if [ ! -f "$PIPER_MODEL" ]; then
    echo "Downloading Piper TTS model..."
    wget -O "$PIPER_MODEL" \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/GB/northern_english/male/medium/en_GB-northern_english-male-medium.onnx"
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
fi

echo "Installation complete."
chmod +x _run.sh