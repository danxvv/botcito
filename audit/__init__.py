"""
Discord Bot Audit CLI - TUI for monitoring bot activity.

Usage:
    uv run audit
"""

import sys

from dotenv import load_dotenv

from .app import AuditApp
from .database import init_db
from .environment import validate_environment, MissingEnvironmentVariableError

__all__ = ["AuditApp", "run_audit"]


def run_audit() -> None:
    """Entry point for the audit CLI."""
    load_dotenv()

    try:
        config = validate_environment()
    except MissingEnvironmentVariableError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Initialize database
    init_db()

    # Run the TUI
    app = AuditApp(discord_token=config.discord_token)
    app.run()


if __name__ == "__main__":
    run_audit()
