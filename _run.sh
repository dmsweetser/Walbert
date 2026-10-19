#!/bin/bash
# Walbert run script

mkdir -p instance/conversations

export ALSA_CONFIG_PATH=/dev/null

# Android/Termux: llama.cpp needs its .so files on LD_LIBRARY_PATH
if [ -d "instance/llama.cpp/bin" ]; then
    export LD_LIBRARY_PATH="$(pwd)/instance/llama.cpp/bin:${LD_LIBRARY_PATH:-}"
fi

source venv/bin/activate
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 main.py
fi
