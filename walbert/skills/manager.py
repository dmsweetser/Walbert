"""
Skill manager implementation
"""

import tempfile
import subprocess
import os
import logging
import re
import json
import base64
from typing import Dict, Any

logger = logging.getLogger('walbert.skills')

class SkillManager:
    """Manages skill execution"""
    def __init__(self, db):
        self.db = db

    def extract_requirements(self, skill_code: str) -> str:
        """Extract requirements from skill code"""
        requirements = []
        in_requirements = False
        lines = skill_code.split('\n')

        for line in lines:
            if line.strip().startswith('# REQUIREMENTS'):
                # Start collecting requirements
                in_requirements = True
                continue
            if in_requirements:
                if line.strip().startswith('#'):
                    # Remove comment marker and whitespace
                    req = line.strip()[1:].strip()
                    if req:
                        requirements.append(req)
                elif line.strip():
                    # End of requirements section
                    break

        return '\n'.join(requirements)

    def install_requirements(self, requirements: str) -> bool:
        """Install requirements in a temporary virtual environment"""
        if not requirements.strip():
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            venv_path = os.path.join(temp_dir, 'venv')
            try:
                # Create virtual environment
                subprocess.run(
                    ['python3', '-m', 'venv', venv_path],
                    check=True,
                    capture_output=True
                )

                # Install pip if not present
                pip_path = os.path.join(venv_path, 'bin', 'pip')
                subprocess.run(
                    [pip_path, '--version'],
                    capture_output=True
                )

                # Install requirements
                result = subprocess.run(
                    [pip_path, 'install'] + requirements.split(),
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    logger.error(f"Failed to install requirements: {result.stderr}")
                    return False

                return True
            except Exception as e:
                logger.error(f"Error installing requirements: {e}")
                return False

    def execute_skill(self, skill_code: str, params: str = "") -> str:
        """Execute a skill in sandboxed environment with parameters"""
        logger.debug(f"Starting skill execution with params: {params}")

        # Parse parameters into state object
        state = {}
        if params:
            try:
                state = json.loads(params)
            except json.JSONDecodeError:
                # Handle simple key=value parameters
                for param in params.split():
                    if '=' in param:
                        key, value = param.split('=', 1)
                        state[key] = value

        requirements = self.extract_requirements(skill_code)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create skill file
            skill_path = os.path.join(temp_dir, 'skill.py')
            with open(skill_path, 'w') as f:
                f.write(skill_code)

            try:
                # Install requirements if any
                if requirements:
                    logger.debug(f"Installing requirements: {requirements}")
                    if not self.install_requirements(requirements):
                        logger.error("Failed to install requirements for skill")
                        return json.dumps({"error": "Failed to install requirements for skill"})

                # Create input file with state
                input_path = os.path.join(temp_dir, 'input.json')
                with open(input_path, 'w') as f:
                    json.dump(state, f)

                # Execute skill with input file
                logger.debug(f"Executing skill with command: python3 {skill_path} {input_path}")
                result = subprocess.run(
                    ['python3', skill_path, input_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir
                )

                logger.debug(f"Skill execution completed with return code: {result.returncode}")
                logger.debug(f"Skill stdout: {result.stdout}")
                logger.debug(f"Skill stderr: {result.stderr}")

                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    logger.error(f"Skill execution failed: {error_msg}")
                    return json.dumps({"error": error_msg})

                # Try to parse the output as JSON
                try:
                    output_state = json.loads(result.stdout)
                    return json.dumps(output_state)
                except json.JSONDecodeError:
                    # If not JSON, return as string
                    return json.dumps({"result": result.stdout if result.stdout else "Skill executed successfully with no output"})

            except subprocess.TimeoutExpired:
                logger.error("Skill execution timed out")
                return json.dumps({"error": "Skill execution timed out"})
            except Exception as e:
                logger.error(f"Skill execution error: {e}")
                return json.dumps({"error": str(e)})
