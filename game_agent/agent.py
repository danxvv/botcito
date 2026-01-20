"""Main GameAgent class implementation using Agno Teams."""

import asyncio
import json
from typing import AsyncGenerator

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.media import Audio
from agno.models.openrouter import OpenRouter

from settings import get_llm_model

from .config import get_memory_db_path
from .environment import ApiKeys, validate_environment
from .mcp_client import MCPConnection
from .session import create_session_context
from .team_factory import create_game_team, create_voice_decision_agent


class GameAgent:
    """
    Team-based agent for answering video game questions.

    Uses a team of specialist agents (Strategy, Build, Lore, Speedrun)
    coordinated by a team leader that routes questions to the best specialist.

    Attributes:
        db: SQLite database for team memory storage
        api_keys: Validated API keys for external services
    """

    def __init__(self) -> None:
        """
        Initialize the game agent team.

        Raises:
            MissingEnvironmentVariableError: If required environment variables are missing
        """
        self.api_keys: ApiKeys = validate_environment()
        self.db: SqliteDb = SqliteDb(db_file=str(get_memory_db_path()))
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the asyncio lock (lazy initialization)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def ask(
        self, guild_id: int, user_id: int, question: str
    ) -> AsyncGenerator[str, None]:
        """
        Ask the team a gaming question with streaming response.

        The team leader analyzes the question and routes it to the
        most appropriate specialist (Strategy, Build, Lore, or Speedrun).

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

        async with self._get_lock():
            async with MCPConnection(self.api_keys.exa_api_key) as mcp_tools:
                team = create_game_team(self.db, mcp_tools)

                async for event in team.arun(
                    input=question,
                    user_id=session.user_id_str,
                    session_id=session.session_id,
                    stream=True,
                ):
                    if hasattr(event, "content") and event.content:
                        yield event.content

    async def ask_simple(self, guild_id: int, user_id: int, question: str) -> str:
        """
        Ask the team a gaming question and get full response.

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

    async def ask_audio(
        self, guild_id: int, user_id: int, audio_data: bytes, audio_format: str = "wav"
    ) -> AsyncGenerator[str, None]:
        """
        Ask the team a question via audio input with streaming response.

        Args:
            guild_id: Discord guild ID for session context
            user_id: Discord user ID for per-user memory isolation
            audio_data: Raw audio bytes (WAV or MP3)
            audio_format: Audio format - "wav" or "mp3"

        Yields:
            Chunks of the response as they are generated
        """
        session = create_session_context(guild_id, user_id)

        async with self._get_lock():
            async with MCPConnection(self.api_keys.exa_api_key) as mcp_tools:
                team = create_game_team(self.db, mcp_tools)

                async for event in team.arun(
                    input="Listen to the audio and respond to the user's question or request.",
                    audio=[Audio(content=audio_data, format=audio_format)],
                    user_id=session.user_id_str,
                    session_id=session.session_id,
                    stream=True,
                ):
                    if hasattr(event, "content") and event.content:
                        yield event.content

    async def ask_audio_simple(
        self, guild_id: int, user_id: int, audio_data: bytes, audio_format: str = "wav"
    ) -> str:
        """
        Ask the team a question via audio and get full response.

        Args:
            guild_id: Discord guild ID for session context
            user_id: Discord user ID for per-user memory isolation
            audio_data: Raw audio bytes (WAV or MP3)
            audio_format: Audio format - "wav" or "mp3"

        Returns:
            The complete response string
        """
        chunks = []
        async for chunk in self.ask_audio(guild_id, user_id, audio_data, audio_format):
            chunks.append(chunk)
        return "".join(chunks)

    async def should_speak(
        self, question: str, user_in_voice: bool
    ) -> tuple[bool, str]:
        """
        Determine if the response should be spoken via TTS.

        Uses the Voice Advisor agent to analyze the context and decide
        if voice output is appropriate.

        Args:
            question: The user's question
            user_in_voice: Whether the user is in a voice channel

        Returns:
            Tuple of (should_speak, reason)
        """
        # Quick check: if not in voice, can't speak
        if not user_in_voice:
            return False, "User not in voice channel"

        # Create voice decision agent using factory
        voice_agent = create_voice_decision_agent()

        # Build context for the agent
        context = f"""Context:
- User is in voice channel: {user_in_voice}
- Question: {question}

Decide if this response should be spoken aloud."""

        # Get decision
        chunks = []
        async for event in voice_agent.arun(input=context, stream=True):
            if hasattr(event, "content") and event.content:
                chunks.append(event.content)

        response = "".join(chunks).strip()

        parsed = self._parse_voice_decision(response)
        if parsed is not None:
            return parsed

        return True, "Default: user is in voice channel"

    def _parse_voice_decision(self, response: str) -> tuple[bool, str] | None:
        """
        Parse JSON response from voice decision agent.

        Args:
            response: Raw response text that may contain JSON

        Returns:
            Tuple of (should_speak, reason) if valid, None if parsing fails
        """
        text = response

        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                inner_parts = parts[1].split("```")
                if inner_parts:
                    text = inner_parts[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                text = parts[1].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        should_speak = data.get("should_speak")
        if not isinstance(should_speak, bool):
            return None

        reason = data.get("reason", "No reason provided")
        if not isinstance(reason, str):
            reason = "No reason provided"

        return should_speak, reason

    async def transcribe_audio(
        self, audio_data: bytes, audio_format: str = "wav"
    ) -> str:
        """
        Transcribe audio without generating a full response.

        This is used for wake word detection to avoid wasting tokens
        on non-triggered speech.

        Args:
            audio_data: Raw audio bytes (WAV or MP3)
            audio_format: Audio format - "wav" or "mp3"

        Returns:
            The transcribed text from the audio
        """
        # Create a simple agent just for transcription (no MCP tools needed)
        transcription_agent = Agent(
            model=OpenRouter(id=get_llm_model(), api_key=self.api_keys.openrouter_api_key),
            instructions="Transcribe the audio exactly as spoken. Output only the transcription, nothing else.",
        )

        # Run transcription
        chunks = []
        async for event in transcription_agent.arun(
            input="Transcribe this audio exactly as spoken.",
            audio=[Audio(content=audio_data, format=audio_format)],
            stream=True,
        ):
            if hasattr(event, "content") and event.content:
                chunks.append(event.content)

        return "".join(chunks)
