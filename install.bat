@echo off
:: Walbert Windows Installation Script

echo Setting up Walbert...

:: Install Python dependencies
python -m pip install --upgrade pip setuptools wheel

:: Create directories
mkdir instance 2>NUL
mkdir instance\conversations 2>NUL
mkdir instance\llama.cpp\bin 2>NUL
mkdir instance\models 2>NUL

:: Create virtual environment
python -m venv venv

:: Activate virtual environment
call venv\Scripts\activate

:: Install Python packages
pip install -r requirements.txt

echo Select a model:
echo 1) Devstral-24B-Instruct-GGUF (Default)
echo 2) Qwen3.6-35B-A3B
echo 3) Ministral 3 - 8B
echo 4) Ministral 3 - 3B
set /p model_choice="Enter choice: "

set MODEL_PATH=
set MMPROJ_PATH=
set CONTEXT_SIZE=
set OUTPUT_TOKENS=
set TEMPERATURE=
set TOP_P=
set TOP_K=
set MIN_P=

if "%model_choice%"=="2" (
    set MODEL_PATH=instance\models\Qwen3.6-35B-A3B-UD-IQ3_S.gguf
    set MMPROJ_PATH=instance\models\Qwen3.6-35B-A3B-UD-IQ3_S-mmproj-BF16.gguf
    set CONTEXT_SIZE=32768
    set OUTPUT_TOKENS=16384
    set TEMPERATURE=0.7
    set TOP_P=0.8
    set TOP_K=20
    set MIN_P=0.0
) else if "%model_choice%"=="3" (
    set MODEL_PATH=instance\models\Ministral-3-8B-Instruct-2512-Q4_K_M.gguf
    set MMPROJ_PATH=instance\models\Ministral-3-8B-Instruct-2512-Q4_K_M-mmproj-BF16.gguf
    set CONTEXT_SIZE=32768
    set OUTPUT_TOKENS=16384
    set TEMPERATURE=0.7
    set TOP_P=0.9
    set TOP_K=40
    set MIN_P=0.00
) else if "%model_choice%"=="4" (
    set MODEL_PATH=instance\models\Ministral-3-3B-Instruct-2512-Q4_K_M.gguf
    set MMPROJ_PATH=
    set CONTEXT_SIZE=32768
    set OUTPUT_TOKENS=16384
    set TEMPERATURE=0.7
    set TOP_P=0.9
    set TOP_K=40
    set MIN_P=0.00
) else (
    set MODEL_PATH=instance\models\Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf
    set MMPROJ_PATH=instance\models\Devstral-Small-2-24B-Instruct-2512-mmproj-BF16.gguf
    set CONTEXT_SIZE=32768
    set OUTPUT_TOKENS=16384
    set TEMPERATURE=0.7
    set TOP_P=0.9
    set TOP_K=40
    set MIN_P=0.05
)

:: Download model files if missing
if not exist "%MODEL_PATH%" (
    echo Downloading model...
    powershell -Command "Invoke-WebRequest -Uri 'https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf?download=true' -OutFile '%MODEL_PATH%'"
)

if not exist "%MMPROJ_PATH%" (
    echo Downloading mmproj...
    powershell -Command "Invoke-WebRequest -Uri 'https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/resolve/main/mmproj-BF16.gguf?download=true' -OutFile '%MMPROJ_PATH%'"
)

:: Download Piper TTS model
set PIPER_MODEL=instance\models\en_GB-northern_english_male-medium.onnx
if not exist "%PIPER_MODEL%" (
    echo Downloading Piper TTS model...
    powershell -Command "Invoke-WebRequest -Uri 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/GB/northern_english/male/medium/en_GB-northern_english-male-medium.onnx' -OutFile '%PIPER_MODEL%'"
)

echo Configure Bluetooth Audio Device:
set /p bt_choice="Enable Bluetooth audio routing? (y/n) [n]: "
if "%bt_choice%"=="y" (
    set bt_enabled=true
    set BT_DEVICE="null"
    set BT_SINK="null"
    set BT_SOURCE="null"
) else (
    set bt_enabled=false
    set BT_DEVICE="null"
    set BT_SINK="null"
    set BT_SOURCE="null"
)

:: Write config.json
(
echo {
echo     "model_configs": {
echo         "model": {
echo             "model_path": "%MODEL_PATH%",
echo             "context_size": %CONTEXT_SIZE%,
echo             "output_tokens": %OUTPUT_TOKENS%,
echo             "temperature": %TEMPERATURE%,
echo             "top_p": %TOP_P%,
echo             "top_k": %TOP_K%,
echo             "min_p": %MIN_P%
echo         }
echo     },
echo     "llama_binary_path": "instance/llama.cpp/bin/llama-completion",
echo     "mmproj_path": "%MMPROJ_PATH%",
echo     "piper_model": "%PIPER_MODEL%",
echo     "log_level": "DEBUG",
echo     "server_port": 8080,
echo     "server_health_check_timeout": 2,
echo     "server_startup_timeout": 60,
echo     "python_execution_timeout": 30,
echo     "autonomous_operation_timeout": 120,
echo     "conversation_log_dir": "instance/conversations",
echo     "walbert_port": 8081,
echo     "udp_port": 9999,
echo     "be_presbyterian": true,
echo     "peer_communication_enabled": false,
echo     "python_execution_enabled": false,
echo     "bash_execution_enabled": false,
echo     "audio_enabled": %bt_enabled%,
echo     "stt_enabled": %bt_enabled%,
echo     "tts_enabled": %bt_enabled%,
echo     "bluetooth_device": "%BT_DEVICE%",
echo     "bluetooth_sink": "%BT_SINK%",
echo     "bluetooth_source": "%BT_SOURCE%",
echo     "stt_timeout": 30,
echo     "user_input_timeout": 60,
echo     "tts_voice": "default",
echo     "database_path": "instance/walbert.db"
echo }
) > instance\config.json

echo Created default config at instance\config.json
echo Please edit this file with your specific paths before running Walbert

:: Download llama.cpp binary
if not exist "instance\llama.cpp\bin\llama-server.exe" (
    echo Downloading llama.cpp binary...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/ggml-org/llama.cpp/releases/download/b9279/llama-b9279-bin-windows-x64.zip' -OutFile 'llama.cpp.zip'"
    powershell -Command "Expand-Archive -Path 'llama.cpp.zip' -DestinationPath 'instance\llama.cpp\bin' -Force"
    del llama.cpp.zip
) else (
    echo llama.cpp already exists, skipping download.
)

echo Installation complete
echo Please edit instance\config.json with your specific paths before running Walbert

echo.
echo Installation complete. Run _run.bat to start Walbert.