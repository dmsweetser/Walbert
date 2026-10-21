"""
Walbert - Local AI Agent
Main entry point for the Walbert AI agent system (headless-aware)
"""

import select
import sys
import os
import logging
import json
import threading
import queue

from walbert.agent import WalbertAgent
from walbert.config import Config
from walbert.model_config import ModelConfig

# Module-level logger so load_config() can use it before main() runs
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
                walbert_port=config_data.get('walbert_port', 8081),
                udp_port=config_data.get('udp_port', 9999),
                bluetooth_device=config_data.get('bluetooth_device', None),
                be_presbyterian=bool(config_data.get('be_presbyterian', True)),
                peer_communication_enabled=bool(config_data.get('peer_communication_enabled', False)),
                python_execution_enabled=bool(config_data.get('python_execution_enabled', False)),
                bash_execution_enabled=bool(config_data.get('bash_execution_enabled', False)),
                user_input_timeout=int(config_data.get('user_input_timeout', 60))
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
    Falls back to line-based read when no TTY is available (headless/SSH mode).
    """
    print(prompt, end='', flush=True)
    # Check if we have a TTY; if not, use simple line read
    if not sys.stdin.isatty():
        try:
            line = sys.stdin.readline()
            if not line:
                return ''
            return line.rstrip('\n\r')
        except KeyboardInterrupt:
            print(f"{chr(10)}Interrupting...")
            raise
    # TTY mode: interactive character-by-character read
    import readchar
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
            print(f"{chr(10)}Interrupting...")
            raise
    return ''.join(user_input)


def print_welcome_message(agent):
    # Print welcome message and ASCII art
    print(r"""
 ___            ___
\   \          /   \
\__   \        /  __/
_\   \      /  __/
 \___\______/   __/
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
    print("- python on/off: Toggle Python execution")
    print("- bash on/off: Toggle Bash execution")
    print("- peer on/off: Toggle peer communication")
    print("- log on/off: Toggle raw block output to console")
    print("- show self_awareness: View consolidated identity, goals, and blockers")
    print("- show user_awareness: View user awareness")
    print("- show user_directive: View user directive")
    print("- show peer_awareness: View awareness of active peers")
    print("- show schema: View database schema")
    print("- list tools: List all available tools")
    print("- pip_install <package>: Install a Python package in the main environment")
    print("- help: Show these options again")
    print("- Any other input will be treated as a request to Walbert")
    print(f"{chr(10)}Status: Python={'ON' if agent.config.python_execution_enabled else 'OFF'}, Bash={'ON' if agent.config.bash_execution_enabled else 'OFF'}, Peer={'ON' if agent.config.peer_communication_enabled else 'OFF'}, Tools={'ON' if agent.tools_enabled else 'OFF'}, Waiting_For_User={'YES' if agent.waiting_for_user else 'NO'}")
    print("")


def _paged_output(text):
    lines = text.split('\n')
    idx = 0
    print(f"{chr(10)}--- PAGED OUTPUT (n=next, p=prev, q=exit) ---")
    while idx < len(lines):
        chunk = lines[idx:idx+10]
        for line in chunk:
            print("*** " + line)
        idx += 10
        if idx >= len(lines):
            print("--- END OF OUTPUT ---")
            break
        print(f"{chr(10)}[Press n for next, p for prev, q to exit] ", end='', flush=True)
        # Skip interactive paging in headless mode; just continue
        if not sys.stdin.isatty():
            continue
        try:
            import readchar
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
    print(f"{chr(10)}")


def run_main_loop(agent, input_queue):
    """Shared main loop logic for both headless and non-headless modes."""
    try:
        while True:
            user_input = None
            # First, check for file-based input (headless/audio mode)
            if os.path.exists('input.txt'):
                try:
                    with open('input.txt', 'r', encoding='utf-8') as f:
                        user_input = f.read().strip()
                    os.remove('input.txt')
                except Exception:
                    pass
            # Only check stdin if we don't have file input yet
            if user_input is None and not sys.stdin.isatty():
                # Non-TTY: use blocking readline (handles EOF cleanly)
                try:
                    line = sys.stdin.readline()
                    if line:
                        user_input = line.rstrip('\n\r')
                except KeyboardInterrupt:
                    print(f"{chr(10)}Interrupting...")
                    raise
            elif user_input is None:
                # TTY mode: use select + readchar
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    user_input = get_nonblocking_input()

            if user_input is None:
                # No input from any source, continue waiting
                continue

            if user_input.lower() in ['exit', 'quit']:
                input_queue.put(("exit",))
                break
            elif user_input.lower() == 'help':
                print_welcome_message(agent)
            elif user_input.lower() == 'python on':
                agent.config.python_execution_enabled = True
                print(f"{chr(10)}Python execution enabled.")
            elif user_input.lower() == 'python off':
                agent.config.python_execution_enabled = False
                print(f"{chr(10)}Python execution disabled.")
            elif user_input.lower() == 'bash on':
                agent.config.bash_execution_enabled = True
                print(f"{chr(10)}Bash execution enabled.")
            elif user_input.lower() == 'bash off':
                agent.config.bash_execution_enabled = False
                print(f"{chr(10)}Bash execution disabled.")
            elif user_input.lower() == 'peer on':
                agent.enable_peer_communication()
            elif user_input.lower() == 'peer off':
                agent.disable_peer_communication()
            elif user_input.lower() == 'log on':
                agent.print_raw = True
                print(f"{chr(10)}Raw log output enabled. All block executions will be printed.")
            elif user_input.lower() == 'log off':
                agent.print_raw = False
                print(f"{chr(10)}Raw log output disabled. Only console responses will be shown.")
            elif user_input.lower() == 'tools on':
                agent.tools_enabled = True
                print(f"{chr(10)}Tool calling enabled.")
            elif user_input.lower() == 'tools off':
                agent.tools_enabled = False
                print(f"{chr(10)}Tool calling disabled.")
            elif user_input.lower() == 'show user_awareness':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- AWARENESS ---\n{agent.state._user_awareness}\n--- END ---")
                else:
                    print(f"{chr(10)}No awareness data available yet.")
            elif user_input.lower() == 'show ultimate_task':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- ULTIMATE_TASK ---\n{agent.state._ultimate_task}\n--- END ---")
                else:
                    print(f"{chr(10)}No ultimate task data available yet.")
            elif user_input.lower() == 'show immediate_task':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- IMMEDIATE_TASK ---\n{agent.state._immediate_task}\n--- END ---")
                else:
                    print(f"{chr(10)}No immediate task data available yet.")
            elif user_input.lower() == 'show impediment':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- IMPEDIMENT ---\n{agent.state._impediment}\n--- END ---")
                else:
                    print(f"{chr(10)}No impediment data available yet.")
            elif user_input.lower() == 'show user_directive':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- USER DIRECTIVE ---\n{agent.state._user_directive}\n--- END ---")
                else:
                    print(f"{chr(10)}No user directive data available yet.")
            elif user_input.lower() == 'show schema':
                if hasattr(agent, 'state') and agent.state:
                    _paged_output(f"--- DB SCHEMA ---\n{agent.state.db_schema}\n--- END ---")
                else:
                    print(f"{chr(10)}No schema data available yet.")
            elif user_input.lower() == 'list tools':
                if hasattr(agent, 'tools') and agent.tools:
                    tools_text = agent.tools.to_prompt_format()
                    _paged_output(tools_text)
                else:
                    print(f"{chr(10)}Tools not initialized.")
            elif user_input.lower().startswith('pip_install '):
                package = user_input[12:].strip()
                if package:
                    agent._install_python_package(package)
                    print(f"{chr(10)}Package installation command executed.")
            elif user_input == "":
                # EOF on stdin (pipe closed) — exit cleanly
                print(f"{chr(10)}Goodbye!")
                break
            else:
                # Put user input into queue for agent
                print(f"{chr(10)}Walbert has received your request.")
                print("Press ENTER to interrupt Walbert at any time.")
                input_queue.put(("user_input", user_input))
    except KeyboardInterrupt:
        print(f"{chr(10)}Goodbye!")
        input_queue.put(("exit",))
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        agent.shutdown()


def main():
    """Main entry point"""
    # Initialize logging
    os.makedirs('instance', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('instance/walbert.log')
        ]
    )

    config = load_config()
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create input/output queue and interrupt event
    input_queue = queue.Queue()
    interrupt_event = threading.Event()

    # Create agent
    agent = WalbertAgent(config, input_queue=input_queue)

    # Start agent in autonomous mode in separate thread
    agent_thread = threading.Thread(target=agent.run_autonomous, args=(input_queue, interrupt_event))
    agent_thread.daemon = True
    agent_thread.start()

    print_welcome_message(agent)

    run_main_loop(agent, input_queue)


if __name__ == "__main__":
    main()
