#!/bin/bash
# Walbert run script

mkdir -p instance/conversations

export ALSA_CONFIG_PATH=/dev/null

source venv/bin/activate
if [ "$1" = "test" ]; then
    sudo python3 -m unittest discover -v
else
    sudo python3 main.py
fi
