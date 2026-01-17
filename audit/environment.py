"""Environment validation for audit CLI."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditConfig:
    """Configuration from environment variables."""
    discord_token: str


class MissingEnvironmentVariableError(ValueError):
    """Raised when a required environment variable is missing."""
    pass


def validate_environment() -> AuditConfig:
    """
    Validate required environment variables.

    Returns:
        AuditConfig with validated values

    Raises:
        MissingEnvironmentVariableError: If DISCORD_TOKEN is not set
    """
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise MissingEnvironmentVariableError(
            "DISCORD_TOKEN environment variable is required. "
            "Set it in your .env file."
        )
    return AuditConfig(discord_token=token)
