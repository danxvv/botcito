"""
Game agent package for video game help with web search capabilities.

This package provides a team-based gaming assistant using Agno Teams,
with specialist agents for Strategy, Builds, Lore, and Speedrunning.

Modules:
    config: Configuration constants and agent configs
    environment: Environment validation and API key management
    mcp_client: MCP tools connection lifecycle management
    team_factory: Team and specialist agent creation
    session: Session context management

Usage:
    from game_agent import GameAgent

    agent = GameAgent()

    # Ask a question (routes to best specialist)
    async for chunk in agent.ask(guild_id, user_id, "How do I beat Malenia?"):
        print(chunk, end="")

    # Check if response should be spoken
    should_speak, reason = await agent.should_speak(question, user_in_voice=True)
"""

from .agent import GameAgent
from .config import AGENT_INSTRUCTIONS, TEAM_INSTRUCTIONS
from .environment import ApiKeys, MissingEnvironmentVariableError, validate_environment
from .session import SessionContext, create_session_context
from .team_factory import create_game_team

__all__ = [
    "GameAgent",
    "AGENT_INSTRUCTIONS",
    "TEAM_INSTRUCTIONS",
    "ApiKeys",
    "MissingEnvironmentVariableError",
    "validate_environment",
    "SessionContext",
    "create_session_context",
    "create_game_team",
]
