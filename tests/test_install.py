"""Tests for the installer script."""
import pytest
import subprocess
import os
import json
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class TestInstaller:
    """Test the installer script."""

    @pytest.fixture
    def install_sh(self):
        return PROJECT_ROOT / "_install.sh"

    @pytest.fixture
    def run_sh(self):
        return PROJECT_ROOT / "_run.sh"

    def test_install_script_exists(self, install_sh):
        assert install_sh.exists()

    def test_run_script_exists(self, run_sh):
        assert run_sh.exists()

    def test_run_script_has_test_mode(self, run_sh):
        content = run_sh.read_text()
        assert "test" in content
        assert "unittest" in content

    def test_install_has_model_options(self, install_sh):
        content = install_sh.read_text()
        assert "Devstral" in content
        assert "Qwen3.6" in content
        assert "Ministral" in content
        assert "Qwen3.5-4B" in content
        assert "Qwen3.5-4B-IQ4_XS" in content

    def test_install_config_json_structure(self, install_sh):
        """Verify the config.json structure that the installer creates."""
        content = install_sh.read_text()
        
        # Check that all expected config keys are present
        expected_keys = [
            "model_configs",
            "llama_binary_path",
            "mmproj_path",
            "log_level",
            "walbert_port",
            "database_path",
            "peer_communication_enabled",
            "python_execution_enabled",
            "bash_execution_enabled",
        ]
        for key in expected_keys:
            assert f'"{key}"' in content, f"Missing config key: {key}"

    def test_install_qwen35_config(self, install_sh):
        """Verify Qwen3.5-4B model has correct config."""
        content = install_sh.read_text()
        
        # Find the Qwen3.5-4B section
        assert 'model_choice" == "5"' in content
        assert "Qwen3.5-4B-IQ4_XS.gguf" in content
        assert "Qwen3.5-4B-GGUF" in content
        assert "CONTEXT_SIZE=32768" in content
        assert "OUTPUT_TOKENS=8192" in content

    def test_install_default_model(self, install_sh):
        """Verify default model (Devstral) config."""
        content = install_sh.read_text()
        
        assert "Devstral-Small-2-24B-Instruct" in content
        assert "CONTEXT_SIZE=32768" in content
        assert "OUTPUT_TOKENS=16384" in content
        assert "TEMPERATURE=0.7" in content

    def test_install_ministral_8b(self, install_sh):
        """Verify Ministral 3-8B model config."""
        content = install_sh.read_text()
        
        assert 'model_choice" == "3"' in content
        assert "Ministral-3-8B-Instruct" in content

    def test_install_ministral_3b(self, install_sh):
        """Verify Ministral 3-3B model config."""
        content = install_sh.read_text()
        
        assert 'model_choice" == "4"' in content
        assert "Ministral-3-3B-Instruct" in content

    def test_install_qwen36(self, install_sh):
        """Verify Qwen3.6-35B-A3B model config."""
        content = install_sh.read_text()
        
        assert 'model_choice" == "2"' in content
        assert "Qwen3.6-35B-A3B" in content
