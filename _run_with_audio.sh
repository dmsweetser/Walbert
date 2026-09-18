#!/bin/bash
# Walbert run script

# Create named pipes for inter-process communication
STT_PIPE="instance/stt_pipe"
TTS_PIPE="instance/tts_pipe"
mkdir -p instance
rm -f "$STT_PIPE" "$TTS_PIPE"  # Remove old pipes if they exist
mkfifo "$STT_PIPE"
mkfifo "$TTS_PIPE"

# Cleanup function
cleanup() {
    pkill -f "python3 audio_standalone.py"
    pkill -f "python3 main.py"
    rm -f "$STT_PIPE" "$TTS_PIPE"
}
trap cleanup EXIT

mkdir -p instance/conversations

# Remove ALSA override if it causes issues
# export ALSA_CONFIG_PATH=/dev/null

source venv/bin/activate || { echo "[ERROR] Failed to activate virtual environment."; exit 1; }

# Start audio_standalone in the background with unbuffered I/O
python3 -u audio_standalone.py < "$TTS_PIPE" > "$STT_PIPE" &
AUDIO_PID=$!
sleep 2  # Give audio_standalone.py time to start
if ! kill -0 $AUDIO_PID 2>/dev/null; then
    echo "[ERROR] audio_standalone.py failed to start."
    exit 1
fi

# Start main.py with stdin from STT pipe and stdout to TTS pipe
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 -u main.py < "$STT_PIPE" > "$TTS_PIPE"
fi