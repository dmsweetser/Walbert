#!/usr/bin/env python3
"""
Unit tests for skill management
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import SkillManager, DatabaseManager

class TestSkillManager(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.init_schema()
        self.skill_manager = SkillManager(self.db)

    def test_store_and_retrieve_skill(self):
        skill_code = "def test_skill(): return 'test'"
        skill_id = self.skill_manager.store_skill("test_skill", skill_code, ["example", "test"])
        self.assertIsInstance(skill_id, int)

        retrieved_code = self.skill_manager.retrieve_skill("test_skill")
        self.assertEqual(retrieved_code, skill_code)

    @patch('subprocess.run')
    def test_execute_skill(self, mock_run):
        mock_run.return_value = MagicMock(stdout="skill output", stderr="", returncode=0)
        skill_code = """
def main():
    print("Hello from skill")
"""
        result = self.skill_manager.execute_skill(skill_code, ["arg1", "arg2"])
        self.assertEqual(result, "skill output")

    def test_retrieve_nonexistent_skill(self):
        result = self.skill_manager.retrieve_skill("nonexistent_skill")
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
