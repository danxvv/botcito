"""Configuration constants for the game agent."""

from pathlib import Path

# Data directory - absolute path relative to package location
DATA_DIR = Path(__file__).parent.parent / "data"

# Database configuration
MEMORY_DB_FILENAME = "game_memory.db"

# Agent persona configuration
AGENT_NAME = "GameGuide"
AGENT_DESCRIPTION = "A veteran gaming expert who has mastered countless games"
AGENT_ROLE = "Video game assistant specializing in helping players overcome challenges"

# Agent behavior configuration
NUM_HISTORY_RUNS = 5
MCP_CONNECT_TIMEOUT_SECONDS = 30.0

# Exa MCP configuration
EXA_MCP_BASE_URL = "https://mcp.exa.ai/mcp"
EXA_MCP_TOOLS = ["web_search_exa", "crawling"]
EXA_MCP_TRANSPORT = "streamable-http"

# Agent instructions
AGENT_INSTRUCTIONS = """You are a video game expert assistant. You help players with:
- Boss strategies and combat tips
- Build guides and character optimization
- Puzzle solutions and walkthroughs
- Game mechanics explanations
- Hidden secrets and collectibles

Use the Exa search tools to find up-to-date guides, wikis, and community tips.
Always cite sources when possible. Be concise but thorough.
Keep responses under 1500 characters to fit in Discord embeds."""


def ensure_data_directory() -> Path:
    """Ensure the data directory exists and return its path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_memory_db_path() -> Path:
    """Get the full path to the memory database file."""
    return ensure_data_directory() / MEMORY_DB_FILENAME
