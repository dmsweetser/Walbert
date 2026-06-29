#!/usr/bin/env python3
"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system
"""

import select
import sys
import os
import logging
import json
import threading
import time
import queue
from walbert import Config, WalbertAgent
from walbert.config import ModelConfig

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
                be_presbyterian=bool(config_data.get('be_presbyterian', True))
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def main():
    """Main entry point"""
    config = load_config()
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create input/output queue and interrupt event
    input_queue = queue.Queue()
    interrupt_event = threading.Event()

    # Create agent
    agent = WalbertAgent(config)

    # Start agent in autonomous mode in separate thread
    agent_thread = threading.Thread(target=agent.run_autonomous, args=(input_queue, interrupt_event))
    agent_thread.daemon = True
    agent_thread.start()

    # Main console loop
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
    print("- Any other input will be treated as a request to Walbert")
    print("")
    print("Say 'Hey Walbert' to activate voice input, and 'Thanks' to end voice input.")
    print("Press ENTER at any time to interrupt Walbert's current processing.")
    print("")
    print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)

    try:
        while True:
            # Check if there's input available without blocking
            if select.select([sys.stdin], [], [], 0)[0]:
                user_input = sys.stdin.readline().strip()
            else:
                user_input = ""
                time.sleep(0.1)
                continue

            if user_input.lower() in ['exit', 'quit']:
                input_queue.put(("exit",))
                break
            elif user_input.lower() == 'inet on':
                agent.internet_access = True
                print("Internet access enabled for Python execution.")
                print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            elif user_input.lower() == 'inet off':
                agent.internet_access = False
                print("Internet access disabled for Python execution.")
                print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            elif user_input.lower().startswith('pip_install '):
                package = user_input[12:].strip()
                if package:
                    agent._install_python_package(package)
                    print("Package installation command executed.")
                print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            elif user_input == "":
                # User pressed ENTER to interrupt Walbert
                print(f"{chr(10)}Interrupting Walbert...{chr(10)}")
                interrupt_event.set()
                # Wait briefly for interruption to complete
                time.sleep(5)
                interrupt_event.clear()
                print(f"Walbert processing interrupted. Waiting for your input...{chr(10)}")
                print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
            else:
                # Put user input into queue for agent
                print(f"{chr(10)}Walbert has received your request.{chr(10)}")
                print(f"Press ENTER to interrupt Walbert at any time.{chr(10)}")
                interrupt_event.set()
                # Wait briefly for interruption to complete
                time.sleep(5)
                interrupt_event.clear()
                input_queue.put(("user_input", user_input))
                print(f"{chr(10)}{chr(10)}>>>>> ", end='', flush=True)
    except KeyboardInterrupt:
        print(f"{chr(10)}Goodbye!")
        input_queue.put(("exit",))
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        agent.shutdown()

if __name__ == "__main__":
    main()
