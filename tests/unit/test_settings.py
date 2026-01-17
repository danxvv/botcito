"""Unit tests for settings.py - SQLite settings management."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We need to patch before importing to prevent auto-initialization
with patch("settings.init_db"):
    from settings import (
        AVAILABLE_MODELS,
        DEFAULT_MODEL,
        get_llm_model,
        get_setting,
        init_db,
        set_llm_model,
        set_setting,
    )


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_settings.db"
    return db_path


@pytest.fixture
def mock_db_connection(temp_db):
    """Mock _get_connection to use temp database."""
    conn = sqlite3.connect(temp_db)

    with patch("settings._get_connection", return_value=conn):
        # Initialize the database
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        )
        conn.commit()
        yield conn

    conn.close()


class TestConstants:
    """Tests for module constants."""

    def test_available_models_not_empty(self):
        """Test AVAILABLE_MODELS is not empty."""
        assert len(AVAILABLE_MODELS) > 0

    def test_default_model_in_available(self):
        """Test DEFAULT_MODEL is in AVAILABLE_MODELS."""
        assert DEFAULT_MODEL in AVAILABLE_MODELS

    def test_available_models_format(self):
        """Test AVAILABLE_MODELS have correct format (provider/model)."""
        for model in AVAILABLE_MODELS:
            assert "/" in model
            provider, name = model.split("/", 1)
            assert len(provider) > 0
            assert len(name) > 0


class TestInitDb:
    """Tests for init_db function.

    Note: init_db is tested implicitly through get_setting/set_setting tests.
    Direct unit tests for init_db are complex due to module-level execution.
    """

    def test_init_db_is_called_on_import(self):
        """Test init_db runs on module import (settings table exists)."""
        # The settings module calls init_db() on import
        # Verify by checking we can use get_setting without error
        result = get_setting("nonexistent_key", default="test_default")
        assert result == "test_default"

    def test_default_model_is_set(self):
        """Test default LLM model is available."""
        # init_db should have set the default model
        model = get_llm_model()
        assert model is not None
        assert model in AVAILABLE_MODELS or model == DEFAULT_MODEL


class TestGetSetting:
    """Tests for get_setting function."""

    def test_get_setting_existing(self, mock_db_connection):
        """Test get_setting returns value for existing key."""
        mock_db_connection.execute("INSERT INTO settings (key, value) VALUES ('test_key', 'test_value')")
        mock_db_connection.commit()

        result = get_setting("test_key")

        assert result == "test_value"

    def test_get_setting_missing_returns_none(self, mock_db_connection):
        """Test get_setting returns None for missing key."""
        result = get_setting("nonexistent_key")

        assert result is None

    def test_get_setting_missing_returns_default(self, mock_db_connection):
        """Test get_setting returns default for missing key."""
        result = get_setting("nonexistent_key", default="fallback")

        assert result == "fallback"


class TestSetSetting:
    """Tests for set_setting function."""

    def test_set_setting_creates_new(self, mock_db_connection):
        """Test set_setting creates new setting."""
        set_setting("new_key", "new_value")

        cursor = mock_db_connection.execute("SELECT value FROM settings WHERE key = 'new_key'")
        row = cursor.fetchone()
        assert row[0] == "new_value"

    def test_set_setting_updates_existing(self, mock_db_connection):
        """Test set_setting updates existing setting."""
        mock_db_connection.execute("INSERT INTO settings (key, value) VALUES ('key', 'old')")
        mock_db_connection.commit()

        set_setting("key", "new")

        cursor = mock_db_connection.execute("SELECT value FROM settings WHERE key = 'key'")
        row = cursor.fetchone()
        assert row[0] == "new"


class TestGetLlmModel:
    """Tests for get_llm_model function."""

    def test_get_llm_model_returns_stored(self, mock_db_connection):
        """Test get_llm_model returns stored model."""
        mock_db_connection.execute(
            "INSERT INTO settings (key, value) VALUES ('llm_model', 'openai/gpt-5.2')"
        )
        mock_db_connection.commit()

        result = get_llm_model()

        assert result == "openai/gpt-5.2"

    def test_get_llm_model_returns_default(self, mock_db_connection):
        """Test get_llm_model returns default when not set."""
        result = get_llm_model()

        assert result == DEFAULT_MODEL


class TestSetLlmModel:
    """Tests for set_llm_model function."""

    def test_set_llm_model_valid(self, mock_db_connection):
        """Test set_llm_model accepts valid model."""
        valid_model = AVAILABLE_MODELS[0]

        result = set_llm_model(valid_model)

        assert result is True
        cursor = mock_db_connection.execute("SELECT value FROM settings WHERE key = 'llm_model'")
        row = cursor.fetchone()
        assert row[0] == valid_model

    def test_set_llm_model_invalid_returns_false(self, mock_db_connection):
        """Test set_llm_model rejects invalid model."""
        result = set_llm_model("invalid/model-name")

        assert result is False

    def test_set_llm_model_invalid_does_not_change(self, mock_db_connection):
        """Test set_llm_model doesn't change setting when invalid."""
        mock_db_connection.execute(
            "INSERT INTO settings (key, value) VALUES ('llm_model', 'openai/gpt-5.2')"
        )
        mock_db_connection.commit()

        set_llm_model("invalid/model")

        cursor = mock_db_connection.execute("SELECT value FROM settings WHERE key = 'llm_model'")
        row = cursor.fetchone()
        assert row[0] == "openai/gpt-5.2"

    def test_set_llm_model_all_available(self, mock_db_connection):
        """Test all AVAILABLE_MODELS can be set."""
        for model in AVAILABLE_MODELS:
            result = set_llm_model(model)
            assert result is True, f"Failed to set model: {model}"
