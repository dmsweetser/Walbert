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
    kill $AUDIO_PID 2>/dev/null
    rm -f "$STT_PIPE" "$TTS_PIPE"
}
trap cleanup EXIT

mkdir -p instance/conversations

export ALSA_CONFIG_PATH=/dev/null

source venv/bin/activate

# Start audio_standalone in the background
python3 audio_standalone.py < "$TTS_PIPE" > "$STT_PIPE" &
AUDIO_PID=$!

# Start main.py with stdin from STT pipe and stdout to TTS pipe
if [ "$1" = "test" ]; then
    python3 -m unittest discover -v
else
    python3 main.py < "$STT_PIPE" > "$TTS_PIPE"
fi