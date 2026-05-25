"""
Test cases for SkillManager
"""

import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
from walbert.skills.manager import SkillManager
from walbert.database.manager import DatabaseManager

class TestSkillManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)
        self.skill_manager = SkillManager(self.db)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    @patch('subprocess.run')
    def test_execute_skill_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="test output", stderr="", returncode=0)

        result = self.skill_manager.execute_skill("print('test')")
        self.assertEqual(result, "test output")

    @patch('subprocess.run')
    def test_execute_skill_failure(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="test error", returncode=1)

        result = self.skill_manager.execute_skill("invalid code")
        self.assertIn("Error: test error", result)

    @patch('subprocess.run')
    def test_execute_skill_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        result = self.skill_manager.execute_skill("while True: pass")
        self.assertIn("Error: Skill execution timed out", result)

    @patch('subprocess.run')
    def test_execute_skill_exception(self, mock_run):
        mock_run.side_effect = Exception("test exception")

        result = self.skill_manager.execute_skill("print('test')")
        self.assertIn("Error: test exception", result)

if __name__ == "__main__":
    unittest.main()
