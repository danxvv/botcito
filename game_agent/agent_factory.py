"""Factory for creating configured Agno agents."""

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openrouter import OpenRouter
from agno.tools.mcp import MCPTools

from settings import get_llm_model

from .config import (
    AGENT_DESCRIPTION,
    AGENT_INSTRUCTIONS,
    AGENT_NAME,
    AGENT_ROLE,
    NUM_HISTORY_RUNS,
)


def create_game_agent(db: SqliteDb, mcp_tools: MCPTools) -> Agent:
    """
    Create a configured game guide agent.

    Uses the Factory pattern to encapsulate agent creation with all
    required configuration applied consistently.

    Args:
        db: SQLite database for agent memory storage
        mcp_tools: Connected MCP tools instance for web search

    Returns:
        Configured Agent instance ready for use
    """
    return Agent(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        role=AGENT_ROLE,
        add_datetime_to_context=True,
        model=OpenRouter(id=get_llm_model()),
        tools=[mcp_tools],
        db=db,
        instructions=AGENT_INSTRUCTIONS,
        markdown=True,
        enable_user_memories=True,
        add_history_to_context=True,
        num_history_runs=NUM_HISTORY_RUNS,
    )
