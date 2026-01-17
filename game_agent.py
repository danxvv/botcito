"""Game help agent using Agno with Exa MCP for web search."""

import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openrouter import OpenRouter
from agno.tools.mcp import MCPTools

# Ensure data directory exists (use absolute path relative to script)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

AGENT_INSTRUCTIONS = """You are a video game expert assistant. You help players with:
- Boss strategies and combat tips
- Build guides and character optimization
- Puzzle solutions and walkthroughs
- Game mechanics explanations
- Hidden secrets and collectibles

Use the Exa search tools to find up-to-date guides, wikis, and community tips.
Always cite sources when possible. Be concise but thorough.
Keep responses under 1500 characters to fit in Discord embeds."""


class GameAgent:
    """Agent for answering video game questions with web search capabilities."""

    def __init__(self):
        self.db = SqliteDb(db_file=str(DATA_DIR / "game_memory.db"))
        self.exa_api_key = os.getenv("EXA_API_KEY")

        if not self.exa_api_key:
            raise ValueError("EXA_API_KEY environment variable is required")

        if not os.getenv("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

    async def ask(self, guild_id: int, question: str) -> AsyncGenerator[str, None]:
        """
        Ask the agent a gaming question with streaming response.

        Args:
            guild_id: Discord guild ID for per-server memory
            question: The user's gaming question

        Yields:
            Chunks of the response as they are generated
        """
        # Build Exa MCP URL with API key and enabled tools
        exa_url = f"https://mcp.exa.ai/mcp?exaApiKey={self.exa_api_key}&tools=web_search_exa,crawling"

        mcp_tools = MCPTools(
            transport="streamable-http",
            url=exa_url,
        )

        # Connect with timeout to avoid hanging
        await asyncio.wait_for(mcp_tools.connect(), timeout=30.0)

        try:
            agent = Agent(
                name="GameGuide",
                model=OpenRouter(id="google/gemini-3-flash-preview"),
                tools=[mcp_tools],
                db=self.db,
                enable_user_memories=True,
                instructions=AGENT_INSTRUCTIONS,
                markdown=True,
            )

            # Stream the response - arun with stream=True returns an async iterator
            async for event in agent.arun(
                input=question,
                user_id=str(guild_id),
                stream=True,
            ):
                if hasattr(event, "content") and event.content:
                    yield event.content

        finally:
            await mcp_tools.close()

    async def ask_simple(self, guild_id: int, question: str) -> str:
        """
        Ask the agent a gaming question and get full response.

        Args:
            guild_id: Discord guild ID for per-server memory
            question: The user's gaming question

        Returns:
            The complete response string
        """
        chunks = []
        async for chunk in self.ask(guild_id, question):
            chunks.append(chunk)
        return "".join(chunks)


