#!/bin/bash
mkdir -p models
mkdir -p llama.cpp/bin

# Download models
wget -O models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
    "https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf?download=true"

wget -O models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf \
    "https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf?download=true"

wget -O models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf \
    "https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true"

# Download and extract llama.cpp binary
wget -O llama.cpp.tar.gz \
    "https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-ubuntu-x64.tar.gz"
tar -xzf llama.cpp.tar.gz -C llama.cpp/bin --strip-components=1
rm llama.cpp.tar.gz
