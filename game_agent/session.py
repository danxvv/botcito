"""Session and user ID management for agent conversations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """
    Encapsulates session identity for agent conversations.

    Attributes:
        user_id_str: String representation of Discord user ID for per-user memories
        session_id: Combined guild+user ID for per-user conversation history within guild
    """

    user_id_str: str
    session_id: str


def create_session_context(guild_id: int, user_id: int) -> SessionContext:
    """
    Create a session context from Discord guild and user IDs.

    The session context provides proper isolation:
    - user_id_str: Used for per-user memory storage across all guilds
    - session_id: Used for per-user conversation history within a specific guild

    Args:
        guild_id: Discord guild (server) ID
        user_id: Discord user ID

    Returns:
        SessionContext with formatted identifiers
    """
    return SessionContext(
        user_id_str=str(user_id),
        session_id=f"{guild_id}_{user_id}",
    )
