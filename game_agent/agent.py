"""Main GameAgent class implementation."""

from typing import AsyncGenerator

from agno.db.sqlite import SqliteDb

from .agent_factory import create_game_agent
from .config import get_memory_db_path
from .environment import ApiKeys, validate_environment
from .mcp_client import MCPConnection
from .session import create_session_context


class GameAgent:
    """
    Agent for answering video game questions with web search capabilities.

    This class serves as the main interface for the game agent package,
    coordinating the various components to provide a seamless API.

    Attributes:
        db: SQLite database for agent memory storage
        api_keys: Validated API keys for external services
    """

    def __init__(self) -> None:
        """
        Initialize the game agent.

        Raises:
            MissingEnvironmentVariableError: If required environment variables are missing
        """
        self.api_keys: ApiKeys = validate_environment()
        self.db: SqliteDb = SqliteDb(db_file=str(get_memory_db_path()))

    async def ask(
        self, guild_id: int, user_id: int, question: str
    ) -> AsyncGenerator[str, None]:
        """
        Ask the agent a gaming question with streaming response.

        Args:
            guild_id: Discord guild ID for session context
            user_id: Discord user ID for per-user memory isolation
            question: The user's gaming question

        Yields:
            Chunks of the response as they are generated

        Raises:
            ValueError: If question is empty or whitespace only
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        session = create_session_context(guild_id, user_id)

        async with MCPConnection(self.api_keys.exa_api_key) as mcp_tools:
            agent = create_game_agent(self.db, mcp_tools)

            async for event in agent.arun(
                input=question,
                user_id=session.user_id_str,
                session_id=session.session_id,
                stream=True,
            ):
                if hasattr(event, "content") and event.content:
                    yield event.content

    async def ask_simple(self, guild_id: int, user_id: int, question: str) -> str:
        """
        Ask the agent a gaming question and get full response.

        Args:
            guild_id: Discord guild ID for session context
            user_id: Discord user ID for per-user memory isolation
            question: The user's gaming question

        Returns:
            The complete response string
        """
        chunks = []
        async for chunk in self.ask(guild_id, user_id, question):
            chunks.append(chunk)
        return "".join(chunks)
