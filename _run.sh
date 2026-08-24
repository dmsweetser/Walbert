#!/bin/bash
# Walbert run script

mkdir -p instance/conversations

export ALSA_CONFIG_PATH=/dev/null

source venv/bin/activate
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 main.py
fi
