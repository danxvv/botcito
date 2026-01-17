"""Configuration for the Discord bot audit CLI."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AUDIT_DB_FILENAME = "audit.db"


def ensure_data_directory() -> Path:
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_audit_db_path() -> Path:
    """Get the path to the audit database."""
    return ensure_data_directory() / AUDIT_DB_FILENAME
