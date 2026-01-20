"""Factory for creating the GameGuide team of specialists."""

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openrouter import OpenRouter
from agno.team import Team
from agno.tools.mcp import MCPTools

from settings import get_llm_model

from .config import (
    BUILD_AGENT_CONFIG,
    LORE_AGENT_CONFIG,
    NUM_HISTORY_RUNS,
    SPEEDRUN_AGENT_CONFIG,
    STRATEGY_AGENT_CONFIG,
    TEAM_DESCRIPTION,
    TEAM_INSTRUCTIONS,
    TEAM_NAME,
    VOICE_AGENT_CONFIG,
)


def _create_specialist_agent(
    config: dict,
    mcp_tools: MCPTools,
    model_id: str,
) -> Agent:
    """Create a specialist agent from config."""
    return Agent(
        name=config["name"],
        role=config["role"],
        description=config["description"],
        instructions=config["instructions"],
        model=OpenRouter(id=model_id),
        tools=[mcp_tools],
        markdown=True,
        add_name_to_context=True,
    )


def _create_voice_agent(model_id: str) -> Agent:
    """Create the voice decision agent (no tools needed)."""
    return Agent(
        name=VOICE_AGENT_CONFIG["name"],
        role=VOICE_AGENT_CONFIG["role"],
        description=VOICE_AGENT_CONFIG["description"],
        instructions=VOICE_AGENT_CONFIG["instructions"],
        model=OpenRouter(id=model_id),
        markdown=False,  # JSON output
        add_name_to_context=True,
    )


def create_game_team(db: SqliteDb, mcp_tools: MCPTools) -> Team:
    """
    Create the GameGuide team with all specialist agents.

    The team uses route mode (respond_directly=True) where the team leader
    analyzes the question and delegates to the most appropriate specialist.

    Args:
        db: SQLite database for team memory storage
        mcp_tools: Connected MCP tools instance for web search

    Returns:
        Configured Team instance ready for use
    """
    model_id = get_llm_model()

    # Create specialist agents
    strategy_agent = _create_specialist_agent(
        STRATEGY_AGENT_CONFIG, mcp_tools, model_id
    )
    build_agent = _create_specialist_agent(
        BUILD_AGENT_CONFIG, mcp_tools, model_id
    )
    lore_agent = _create_specialist_agent(
        LORE_AGENT_CONFIG, mcp_tools, model_id
    )
    speedrun_agent = _create_specialist_agent(
        SPEEDRUN_AGENT_CONFIG, mcp_tools, model_id
    )

    # Create the team with route mode
    return Team(
        name=TEAM_NAME,
        description=TEAM_DESCRIPTION,
        model=OpenRouter(id=model_id),
        members=[strategy_agent, build_agent, lore_agent, speedrun_agent],
        instructions=TEAM_INSTRUCTIONS,
        db=db,
        markdown=True,
        respond_directly=True,  # Route mode - leader picks one agent
        show_members_responses=False,  # Only show final response
        enable_agentic_context=True,
        add_datetime_to_context=True,
        num_history_runs=NUM_HISTORY_RUNS,
    )


def create_voice_decision_agent() -> Agent:
    """
    Create a standalone voice decision agent.

    This agent analyzes context to decide if a response should be spoken.
    It runs separately from the main team for efficiency.

    Returns:
        Configured Agent for voice decisions
    """
    return _create_voice_agent(get_llm_model())
