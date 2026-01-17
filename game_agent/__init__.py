"""
Game agent package for video game help with web search capabilities.

This package provides a modular implementation of a gaming assistant agent
that uses Agno with Exa MCP for web search functionality.

Modules:
    config: Configuration constants and path management
    environment: Environment validation and API key management
    mcp_client: MCP tools connection lifecycle management
    agent_factory: Agent creation factory
    session: Session context management

Usage:
    from game_agent import GameAgent

    agent = GameAgent()
    async for chunk in agent.ask(guild_id, user_id, "How do I beat Malenia?"):
        print(chunk, end="")
"""

from .agent import GameAgent
from .config import AGENT_INSTRUCTIONS
from .environment import ApiKeys, MissingEnvironmentVariableError, validate_environment
from .session import SessionContext, create_session_context

__all__ = [
    "GameAgent",
    "AGENT_INSTRUCTIONS",
    "ApiKeys",
    "MissingEnvironmentVariableError",
    "validate_environment",
    "SessionContext",
    "create_session_context",
]
