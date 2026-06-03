#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import sys
import os
import logging
import json
import threading
import time
import queue
from walbert import Config, WalbertAgent
from walbert.config import ModelConfig
from walbert.tts import TextToSpeech
from walbert.stt import SpeechToText

# Initialize logging
os.makedirs('instance', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instance/walbert.log')
    ]
)
logger = logging.getLogger('walbert')

def load_config() -> Config:
    """Load system configuration"""
    try:
        with open('instance/config.json', 'r') as f:
            config_data = json.load(f)
            model_configs = {
                'model': ModelConfig(
                    model_path=config_data['model_configs']['model']['model_path'],
                    context_size=config_data['model_configs']['model']['context_size'],
                    output_tokens=config_data['model_configs']['model']['output_tokens'],
                    temperature=config_data['model_configs']['model']['temperature'],
                    top_p=config_data['model_configs']['model']['top_p'],
                    top_k=config_data['model_configs']['model']['top_k'],
                    min_p=config_data['model_configs']['model']['min_p']
                )
            }
            return Config(
                model_configs=model_configs,
                llama_binary_path=config_data['llama_binary_path'],
                mmproj_path=config_data.get('mmproj_path', ""),
                log_level=config_data.get('log_level', "INFO"),
                be_presbyterian=str(config_data.get('be_presbyterian', "true")).lower() == "true"
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def clear_console():
    """Clear the console screen"""
    print("\033[2J\033[H", end='')

def main():
    """Main entry point"""
    config = load_config()
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Initialize TTS and STT
    tts = TextToSpeech()
    stt = SpeechToText()

    # Start STT in continuous listening mode
    stt_start_event = threading.Event()
    stt_thread = threading.Thread(target=stt.start_listening, args=(stt_start_event,))
    stt_thread.daemon = True
    stt_thread.start()

    # Give STT thread time to initialize
    time.sleep(2)
    stt_start_event.set()

    # Create input/output queue
    input_queue = queue.Queue()

    # Create agent
    agent = WalbertAgent(config)

    # Start agent in autonomous mode in separate thread
    agent_thread = threading.Thread(target=agent.run_autonomous, args=(input_queue,))
    agent_thread.daemon = True
    agent_thread.start()

    # Main console loop
    # Clear console before starting
    clear_console()
    print("""
          
 ___            ___      
/   \          /   \    
\_   \        /  __/    
 _\   \      /  /__     
 \___  \____/   __/     
     \_       _/        
       | @ @  \_        
       |                
     _/     /\          
    /o)  (o/\ \_        
    \_____/ /           
      \____/            
          
              """)

    print("Welcome to Walbert! The local-first AI agent.")
    print("Available commands:")
    print("- exit/quit: Exit the program")
    print("- inet on: Enable internet access for Python execution")
    print("- inet off: Disable internet access for Python execution")
    print("- pip_install <package>: Install a Python package in the main environment")
    print("- tts on: Enable text-to-speech")
    print("- tts off: Disable text-to-speech")
    print("- stt on: Enable speech-to-text")
    print("- stt off: Disable speech-to-text")
    print("- continue: Resume autonomous processing after user control")
    print("- Any other input will be treated as a request to Walbert")
    print("")
    print("Say 'Hey Walbert' to activate voice input, and 'Thanks' to end voice input.")
    print("")

    tts_enabled = True
    stt_enabled = True

    try:
        while True:
            # Clear console before getting user input
            clear_console()
            user_input = input("> ")
            if user_input.strip():
                # Handle commands
                if user_input.lower() in ['exit', 'quit']:
                    input_queue.put(("exit",))
                    break
                elif user_input.lower() == 'inet on':
                    agent.internet_access = True
                    print("Internet access enabled for Python execution.")
                elif user_input.lower() == 'inet off':
                    agent.internet_access = False
                    print("Internet access disabled for Python execution.")
                elif user_input.lower().startswith('pip_install '):
                    package = user_input[12:].strip()
                    if package:
                        agent._install_python_package(package)
                        # Clear console after command execution
                        clear_console()
                        print("Package installation command executed.")
                        print("Type 'continue' to resume, or enter a new request.")
                        continue
                elif user_input.lower() == 'tts on':
                    tts_enabled = True
                    # Clear console after command execution
                    clear_console()
                    print("Text-to-speech enabled.")
                elif user_input.lower() == 'tts off':
                    tts_enabled = False
                    # Clear console after command execution
                    clear_console()
                    print("Text-to-speech disabled.")
                elif user_input.lower() == 'stt on':
                    stt_enabled = True
                    stt.resume_listening()
                    # Clear console after command execution
                    clear_console()
                    print("Speech-to-text enabled.")
                elif user_input.lower() == 'stt off':
                    stt_enabled = False
                    stt.pause_listening()
                    # Clear console after command execution
                    clear_console()
                    print("Speech-to-text disabled.")
                elif user_input.lower() == 'continue':
                    # Clear console after command execution
                    clear_console()
                    print("Resuming autonomous processing...")
                    input_queue.put(("user_input", "[walbert_continue_processing]Resuming processing after user input[/walbert_continue_processing]"))
                else:
                    # Put user input into queue for agent
                    input_queue.put(("user_input", user_input))

                    # If TTS is enabled, speak the response
                    if tts_enabled and agent.last_response:
                        tts.speak(agent.last_response)

                    # Check if agent requested user control and wait for continuation
                    if "[walbert_user_control]" in agent.last_response:
                        # Clear console for user control prompt
                        clear_console()
                        print("Walbert has requested user guidance. Please provide input when ready.")
                        print("Type 'continue' when you want Walbert to resume processing.")
                        while True:
                            continuation_input = input("> ")
                            if continuation_input.lower() == 'continue':
                                input_queue.put(("user_input", f"[walbert_continue_processing]{chr(10)}Resuming processing after user guidance{chr(10)}[/walbert_continue_processing]"))
                                break
                            else:
                                input_queue.put(("user_input", continuation_input))
    except KeyboardInterrupt:
        print(f"{chr(10)}Goodbye!")
        input_queue.put(("exit",))
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        agent.shutdown()
        stt.stop()

if __name__ == "__main__":
    main()
