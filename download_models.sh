#!/bin/bash
# Walbert model download script
# Downloads required GGUF models and llama.cpp binary

set -e

# Create directories
mkdir -p models
mkdir -p llama.cpp/bin

# Download primary model
echo "Downloading Ministral-3B model..."
wget -O models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
    "https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf?download=true"
if [ $? -ne 0 ]; then
    echo "Error: Failed to download primary model"
    exit 1
fi

# Download multimodal projector
echo "Downloading multimodal projector..."
wget -O models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf \
    "https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf?download=true"
if [ $? -ne 0 ]; then
    echo "Error: Failed to download multimodal projector"
    exit 1
fi

# Download Devstral model
echo "Downloading Devstral-24B model..."
wget -O models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf \
    "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true"
if [ $? -ne 0 ]; then
    echo "Error: Failed to download Devstral model"
    exit 1
fi

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
tar -xzf llama.cpp.tar.gz -C llama.cpp/bin --strip-components=1
rm llama.cpp.tar.gz
if [ $? -ne 0 ]; then
    echo "Error: Failed to extract llama.cpp binary"
    exit 1
fi

echo "All models and binaries downloaded successfully!"
