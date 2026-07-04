#!/bin/bash
# Walbert run script

mkdir -p instance/conversations

source venv/bin/activate
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 main.py
fi
