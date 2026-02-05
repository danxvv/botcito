"""Environment validation and API key management."""

import os
from dataclasses import dataclass


class MissingEnvironmentVariableError(Exception):
    """Raised when required environment variables are missing."""

    pass


@dataclass(frozen=True)
class ApiKeys:
    """Container for validated API keys."""

    exa_api_key: str
    openrouter_api_key: str


def validate_environment() -> ApiKeys:
    """
    Validate that all required environment variables are set.

    Returns:
        ApiKeys dataclass with validated API keys

    Raises:
        MissingEnvironmentVariableError: If any required environment variable is missing
    """
    exa_api_key = os.getenv("EXA_API_KEY")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    missing_vars = []

    if not exa_api_key:
        missing_vars.append("EXA_API_KEY")

    if not openrouter_api_key:
        missing_vars.append("OPENROUTER_API_KEY")

    if missing_vars:
        raise MissingEnvironmentVariableError(
            f"Required environment variable(s) missing: {', '.join(missing_vars)}"
        )

    return ApiKeys(
        exa_api_key=exa_api_key,
        openrouter_api_key=openrouter_api_key,
    )
