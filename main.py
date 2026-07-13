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
from walbert.agent import WalbertAgent
from walbert.config import Config
from walbert.model_config import ModelConfig

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
                be_presbyterian=bool(config_data.get('be_presbyterian', True)),
                max_context_blocks=config_data['max_context_blocks']
            )
    except FileNotFoundError:
        logger.error("instance/config.json not found")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def get_nonblocking_input(prompt: str = ">>>>> ") -> str:
    """
    Read input from stdin in a non-blocking way, echoing characters as they are typed.
    Supports backspace. Returns the input string when Enter is pressed.
    """
    import readchar
    print(prompt, end='', flush=True)
    user_input = []
    while True:
        try:
            char = readchar.readchar()
            if char == '\n':  # Enter key
                break
            elif char == '\x03':  # Ctrl+C
                raise KeyboardInterrupt
            elif char in ('\x7f', '\x08'):  # Backspace
                if user_input:
                    user_input.pop()
                    print('\b \b', end='', flush=True)
                continue
            user_input.append(char)
            print(char, end='', flush=True)  # Echo the character
        except KeyboardInterrupt:
            print("\nInterrupting...")
            raise
    return ''.join(user_input)

def print_welcome_message():
    # Print welcome message and ASCII art
    print("""          
 ___            ___      
/   \\          /   \\    
\\_   \\        /  __/    
 _\\   \\      /  /__     
 \\___  \\____/   __/     
     \\_       _/        
       | @ @  \\_        
       |                
     _/     /\\          
    /o)  (o/\\ \\_        
    \\_____/ /           
      \\____/                      
              """)

    print("Welcome to Walbert! The local-first AI agent.")
    print("Available commands:")
    print("- exit/quit: Exit the program")
    print("- inet on/off: Toggle internet access for Python execution")
    print("- log on/off: Toggle raw block output to console")
    print("- show awareness/schema/context: View agent state")
    print("- pip_install <package>: Install a Python package in the main environment")
    print("- help: Show these options again")
    print("- Any other input will be treated as a request to Walbert")
    print("")
    
def _paged_output(text):
    import readchar
    lines = text.split('\n')
    idx = 0
    print("\n--- PAGED OUTPUT (n=next, p=prev, q=exit) ---")
    while idx < len(lines):
        chunk = lines[idx:idx+10]
        for line in chunk:
            print(line)
        idx += 10
        if idx >= len(lines):
            print("--- END OF OUTPUT ---")
            break
        print("\n[Press n for next, p for prev, q to exit] ", end='', flush=True)
        try:
            cmd = readchar.readchar()
            if cmd == 'n':
                continue
            elif cmd == 'p':
                idx -= 10
                if idx < 0:
                    idx = 0
                continue
            elif cmd == 'q':
                break
        except KeyboardInterrupt:
            break
    print("\n")

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

    print_welcome_message()

    try:
        while True:
            # Get user input in a non-blocking way
            user_input = get_nonblocking_input()

            if user_input.lower() in ['exit', 'quit']:
                input_queue.put(("exit",))
                break
            elif user_input.lower() == 'help':
                print_welcome_message()
            elif user_input.lower() == 'inet on':
                agent.internet_access = True
                print("\nInternet access enabled for Python execution.")
            elif user_input.lower() == 'inet off':
                agent.internet_access = False
                print("\nInternet access disabled for Python execution.")
            elif user_input.lower() == 'log on':
                agent.print_raw = True
                print("\nRaw log output enabled. All block executions will be printed.")
            elif user_input.lower() == 'log off':
                agent.print_raw = False
                print("\nRaw log output disabled. Only console responses will be shown.")
            elif user_input.lower() == 'show awareness':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- AWARENESS ---\n{agent.state.awareness_text}\n--- END ---")
                else:
                    print("\nNo awareness data available yet.")
            elif user_input.lower() == 'show schema':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- DB SCHEMA ---\n{agent.state.db_schema}\n--- END ---")
                else:
                    print("\nNo schema data available yet.")
            elif user_input.lower() == 'show context':
                if hasattr(agent, 'state') and agent.state:
                    blocks = agent.state.context_blocks
                    ctx = "--- CONTEXT BLOCKS ({}) ---".format(len(blocks))
                    for b in blocks:
                        ctx += "\n[{}]: {}...".format(b['type'], b['content'][:200])
                    ctx += "\n--- END ---"
                    _paged_output(ctx)
                else:
                    print("\nNo context data available yet.")
            elif user_input.lower().startswith('pip_install '):
                package = user_input[12:].strip()
                if package:
                    agent._install_python_package(package)
                    print("\nPackage installation command executed.")
            elif user_input == "":
                continue
            else:
                # Put user input into queue for agent
                print("\nWalbert has received your request.")
                print("Press ENTER to interrupt Walbert at any time.")
                interrupt_event.set()
                time.sleep(0.5)  # Brief pause to allow interruption
                interrupt_event.clear()
                input_queue.put(("user_input", user_input))
    except KeyboardInterrupt:
        print("\nGoodbye!")
        input_queue.put(("exit",))
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        agent.shutdown()

if __name__ == "__main__":
    main()