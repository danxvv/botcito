"""Music discovery agent using Agno for AI-powered recommendations."""

import json
import logging
import re
from dataclasses import dataclass

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

import os

from settings import get_llm_model

from .tools import search_songs, get_song_recommendations

logger = logging.getLogger(__name__)

DISCOVERY_INSTRUCTIONS = """You are a music discovery assistant. Your job is to find songs that match
a user's description of what they want to listen to.

Follow these steps:

1. Analyze the user's description to understand the mood, genre, style, tempo, energy level,
   or specific artists/songs they mention.

2. Generate 2-4 diverse search queries that capture different aspects of what the user wants.
   For example, if someone says "chill vibes for a rainy day", you might search for
   "chill lo-fi rain", "mellow acoustic rainy day", "relaxing ambient piano".

3. Use the search_songs tool for each query to find matching songs.

4. Optionally use get_song_recommendations on particularly good matches to find similar songs
   and expand your pool of candidates.

5. From ALL the results you gathered, select 5-8 of the best matches ranked by how well they
   fit the user's description. Prioritize variety - avoid picking multiple songs by the same
   artist unless the user specifically asked for that artist.

6. Return ONLY a valid JSON object with no markdown formatting, no explanation, no extra text:
{"songs": [{"videoId": "...", "title": "...", "artist": "...", "reason": "short reason"}], "summary": "one sentence describing the playlist vibe"}

Rules:
- Avoid duplicates (same videoId).
- Each "reason" should be under 60 characters and explain why this song fits.
- If the user names specific artists, search for those artists AND similar ones.
- If the description is vague or poetic, interpret the mood and find fitting genres.
- Do NOT wrap the JSON in markdown code blocks. Output raw JSON only.
- Do NOT include any text before or after the JSON object."""


@dataclass
class DiscoveredSong:
    """A single song discovered by the agent."""

    video_id: str
    title: str
    artist: str
    reason: str


@dataclass
class DiscoveryResult:
    """Result from a music discovery request."""

    songs: list[DiscoveredSong]
    summary: str


class MusicDiscoveryAgent:
    """Agent that discovers music based on natural language descriptions.

    Uses an LLM with YouTube Music search tools to find songs matching
    a user's mood, genre, or style description.
    """

    def __init__(self) -> None:
        """Initialize the music discovery agent.

        Raises:
            ValueError: If OPENROUTER_API_KEY environment variable is missing
        """
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required for /discover")
        self._openrouter_api_key = openrouter_key

    def _create_agent(self) -> Agent:
        """Create a fresh Agno Agent for a discovery request."""
        return Agent(
            model=OpenRouter(id=get_llm_model(), api_key=self._openrouter_api_key),
            tools=[search_songs, get_song_recommendations],
            instructions=[DISCOVERY_INSTRUCTIONS],
            markdown=False,
        )

    async def discover(self, description: str) -> DiscoveryResult:
        """Discover songs matching a natural language description.

        Args:
            description: What kind of music the user wants (mood, genre, artist, etc.)

        Returns:
            DiscoveryResult with list of discovered songs and a summary

        Raises:
            ValueError: If description is empty
        """
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")

        agent = self._create_agent()

        chunks: list[str] = []
        async for event in agent.arun(input=description, stream=True):
            if hasattr(event, "content") and event.content:
                chunks.append(event.content)

        raw_response = "".join(chunks)
        cleaned = self._strip_tool_outputs(raw_response)
        return self._parse_response(cleaned)

    def _parse_response(self, raw: str) -> DiscoveryResult:
        """Parse the agent's JSON response into a DiscoveryResult.

        Args:
            raw: Raw text response from the agent

        Returns:
            Parsed DiscoveryResult, or empty result if parsing fails
        """
        text = raw.strip()

        # Check for markdown code blocks
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # Find outermost JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            logger.warning("No JSON object found in response: %s", text[:200])
            return DiscoveryResult(songs=[], summary="Could not parse recommendations.")

        json_str = text[start:end + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON response: %s\nRaw: %s", e, json_str[:300])
            return DiscoveryResult(songs=[], summary="Could not parse recommendations.")

        songs = []
        seen_ids: set[str] = set()
        for item in data.get("songs", []):
            video_id = item.get("videoId", "")
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            songs.append(DiscoveredSong(
                video_id=video_id,
                title=item.get("title", "Unknown"),
                artist=item.get("artist", "Unknown"),
                reason=item.get("reason", ""),
            ))

        summary = data.get("summary", "Here are some songs you might enjoy.")

        return DiscoveryResult(songs=songs, summary=summary)

    def _strip_tool_outputs(self, text: str) -> str:
        """Strip tool debug outputs from text.

        Removes patterns like:
        - "search_songs(query=...) completed in 2.1s"
        - "get_song_recommendations(video_id=...) completed in 1.5s"

        Args:
            text: Text that may contain tool debug outputs

        Returns:
            Text with tool outputs removed
        """
        pattern = r'\w+\([^)]*\)\s+completed\s+in\s+[\d.]+s\.?\s*'
        return re.sub(pattern, '', text)
