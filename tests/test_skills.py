#!/usr/bin/env python3
"""
Unit tests for skill management
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walbert.skills.manager import SkillManager
from walbert.database.manager import DatabaseManager

class TestSkillManager(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_schema()
        self.skill_manager = SkillManager(self.db)

    @patch('subprocess.run')
    def test_execute_skill_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="skill output", stderr="", returncode=0)
        skill_code = """
def main():
    print("Hello from skill")
"""
        result = self.skill_manager.execute_skill(skill_code, ["arg1", "arg2"])
        self.assertEqual(result, "skill output")

    @patch('subprocess.run')
    def test_execute_skill_failure(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="error", returncode=1)
        skill_code = """
def main():
    raise Exception("Test error")
"""
        result = self.skill_manager.execute_skill(skill_code)
        self.assertTrue("Error:" in result)

    @patch('subprocess.run')
    def test_execute_skill_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
        skill_code = """
import time
time.sleep(60)
"""
        result = self.skill_manager.execute_skill(skill_code)
        self.assertEqual(result, "Error: Skill execution timed out")

if __name__ == '__main__':
    unittest.main()
