"""Unit tests for game_agent/environment.py - Environment validation."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Import directly from the file to avoid game_agent/__init__.py cascade
# which triggers agno imports that may have Python version compatibility issues
_module_path = Path(__file__).parent.parent.parent.parent / "game_agent" / "environment.py"
_spec = importlib.util.spec_from_file_location("game_agent_environment", _module_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

ApiKeys = _module.ApiKeys
MissingEnvironmentVariableError = _module.MissingEnvironmentVariableError
validate_environment = _module.validate_environment


class TestApiKeys:
    """Tests for ApiKeys dataclass."""

    def test_api_keys_creation(self):
        """Test ApiKeys creation with valid keys."""
        keys = ApiKeys(
            exa_api_key="test-exa-key",
            openrouter_api_key="test-openrouter-key",
        )
        assert keys.exa_api_key == "test-exa-key"
        assert keys.openrouter_api_key == "test-openrouter-key"

    def test_api_keys_immutable(self):
        """Test ApiKeys is immutable (frozen dataclass)."""
        keys = ApiKeys(
            exa_api_key="key1",
            openrouter_api_key="key2",
        )
        with pytest.raises(AttributeError):
            keys.exa_api_key = "new-key"

    def test_api_keys_equality(self):
        """Test ApiKeys equality comparison."""
        keys1 = ApiKeys(exa_api_key="a", openrouter_api_key="b")
        keys2 = ApiKeys(exa_api_key="a", openrouter_api_key="b")
        keys3 = ApiKeys(exa_api_key="x", openrouter_api_key="y")

        assert keys1 == keys2
        assert keys1 != keys3


class TestMissingEnvironmentVariableError:
    """Tests for MissingEnvironmentVariableError exception."""

    def test_exception_message(self):
        """Test exception carries correct message."""
        error = MissingEnvironmentVariableError("Missing: API_KEY")
        assert str(error) == "Missing: API_KEY"

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        assert issubclass(MissingEnvironmentVariableError, Exception)


class TestValidateEnvironment:
    """Tests for validate_environment function."""

    def test_validate_with_all_keys(self):
        """Test validation passes with all keys present."""
        env = {
            "EXA_API_KEY": "test-exa-key-12345",
            "OPENROUTER_API_KEY": "test-openrouter-key-12345",
        }

        with patch.dict(os.environ, env, clear=True):
            keys = validate_environment()

            assert keys.exa_api_key == "test-exa-key-12345"
            assert keys.openrouter_api_key == "test-openrouter-key-12345"

    def test_validate_missing_exa_key(self):
        """Test validation fails when EXA_API_KEY missing."""
        env = {
            "OPENROUTER_API_KEY": "test-key",
        }

        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(MissingEnvironmentVariableError) as exc_info:
                validate_environment()

            assert "EXA_API_KEY" in str(exc_info.value)

    def test_validate_missing_openrouter_key(self):
        """Test validation fails when OPENROUTER_API_KEY missing."""
        env = {
            "EXA_API_KEY": "test-key",
        }

        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(MissingEnvironmentVariableError) as exc_info:
                validate_environment()

            assert "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_validate_missing_both_keys(self):
        """Test validation fails listing both missing keys."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingEnvironmentVariableError) as exc_info:
                validate_environment()

            error_msg = str(exc_info.value)
            assert "EXA_API_KEY" in error_msg
            assert "OPENROUTER_API_KEY" in error_msg

    def test_validate_empty_key_treated_as_missing(self):
        """Test empty string keys are treated as missing."""
        env = {
            "EXA_API_KEY": "",
            "OPENROUTER_API_KEY": "",
        }

        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(MissingEnvironmentVariableError):
                validate_environment()

    def test_validate_whitespace_only_key(self):
        """Test whitespace-only keys are NOT treated as missing (raw value returned)."""
        env = {
            "EXA_API_KEY": "   ",
            "OPENROUTER_API_KEY": "valid-key",
        }

        with patch.dict(os.environ, env, clear=True):
            # Whitespace is truthy in Python, so it passes
            keys = validate_environment()
            assert keys.exa_api_key == "   "
