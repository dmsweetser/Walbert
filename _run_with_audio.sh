#!/bin/bash
# Walbert run script with simplified file-based IPC

mkdir -p instance/conversations

source venv/bin/activate || { echo "[ERROR] Failed to activate virtual environment."; exit 1; }

# Cleanup function
cleanup() {
    pkill -f "python3 audio_standalone.py" 2>/dev/null
    pkill -f "python3 main.py" 2>/dev/null
    # Explicitly clear IPC files on exit
    rm -f input.txt output.txt
}
trap cleanup EXIT

# Start audio_standalone in the background
python3 audio_standalone.py &
AUDIO_PID=$!
sleep 2
if ! kill -0 $AUDIO_PID 2>/dev/null; then
    echo "[ERROR] audio_standalone.py failed to start."
    exit 1
fi

# Explicitly handle output.txt for TTS only (prevents accidental STT feedback)
(
    while true; do
        if [ -f "output.txt" ]; then
            # Only pass to TTS, never to STT
            cat output.txt > /dev/null
            rm -f output.txt
        fi
        sleep 0.5
    done
) &
TTS_LOOP_PID=$!

# Start main.py
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 main.py
fi