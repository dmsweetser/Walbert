#!/bin/bash
# Walbert run script

# Ensure instance directory exists
mkdir -p instance/conversations/raw
mkdir -p instance/conversations/chat

source venv/bin/activate
python3 main.py
