# AGENTS.md

Guidelines for AI coding agents working in this Discord music bot repository.

## Project Overview

Discord music bot with slash commands, YouTube playback via Opus streaming, autoplay functionality using YouTube Music recommendations, and an AI-powered gaming assistant. Uses Python 3.10+ with async/await patterns throughout.

## Build and Run Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run the bot
uv run python main.py

# Run the audit TUI
uv run audit
```

## External Dependencies

The bot requires these external tools installed on the system:
- **FFmpeg** - Required for audio playback/streaming
- **Deno or Node.js** - Required by yt-dlp for YouTube JavaScript extraction

## Testing

This project currently has no automated tests. When adding tests:
- Place tests in a `tests/` directory
- Use pytest: `uv run pytest tests/`
- Run a single test: `uv run pytest tests/test_file.py::test_function -v`

## Environment Variables

Required in `.env` file:
```
DISCORD_TOKEN=your_bot_token_here
# For /guide command (optional):
EXA_API_KEY=your_exa_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

## Code Style Guidelines

### Imports

- Standard library first, then third-party, then local modules
- Flat import style (no blank lines between groups)
- Use relative imports within packages (e.g., `from .agent_factory import create_game_agent`)

```python
import asyncio
import os
from dataclasses import dataclass

import discord
from discord import app_commands

from autoplay import YouTubeMusicHandler
from music_player import player_manager
```

### Type Hints

Use modern Python 3.10+ syntax throughout:

```python
# Use built-in generics, not typing module
dict[str, Any]           # not Dict[str, Any]
list[SongInfo]           # not List[SongInfo]
str | None               # not Optional[str]
AsyncGenerator[str, None]  # for async generators
```

Always add return type hints to functions:

```python
def format_duration(seconds: int) -> str:
async def extract_song_info(query: str) -> SongInfo | None:
async def ask(self, guild_id: int, user_id: int, question: str) -> AsyncGenerator[str, None]:
```

### Naming Conventions

- `snake_case` for functions, variables, and modules
- `PascalCase` for classes (e.g., `MusicPlayerManager`, `GameAgent`)
- `SCREAMING_SNAKE_CASE` for constants (e.g., `DISCONNECT_TIMEOUT`, `FFMPEG_OPTIONS`)
- Private methods/attributes prefixed with underscore (e.g., `_get_autoplay_song`, `_lock`)

### Docstrings

Use Google-style docstrings:

```python
async def extract_song_info(query: str) -> SongInfo | None:
    """
    Extract song information from a URL or video ID.

    Args:
        query: YouTube URL, video ID, or search query

    Returns:
        SongInfo object or None if extraction failed
    """
```

Module-level docstrings are one-liners:

```python
"""Music player with queue management, autoplay, and auto-disconnect."""
```

### Dataclasses

Heavy use of dataclasses for data containers:

```python
@dataclass
class SongInfo:
    """Information about a song."""
    url: str
    title: str
    duration: int

@dataclass(frozen=True)
class ApiKeys:
    """Container for validated API keys."""
    exa_api_key: str
    openrouter_api_key: str

@dataclass
class GuildPlayer:
    voice_client: discord.VoiceClient | None = None
    queue: deque[SongInfo] = field(default_factory=deque)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
```

### Error Handling

- Raise specific exception types, not generic Exception
- Use try/except with specific exceptions
- Log errors with `logger.exception()` for stack traces
- Limit error message length when displaying to users (e.g., `str(e)[:500]`)

```python
class MissingEnvironmentVariableError(Exception):
    """Raised when required environment variables are missing."""
    pass

# Specific exception handling
try:
    return ydl.extract_info(url, download=False)
except yt_dlp.utils.DownloadError as e:
    error_msg = str(e)
    if "JavaScript" in error_msg:
        print("Error: yt-dlp requires Deno/Node.js for YouTube.")
    return None
except Exception:
    return None
```

### Async Patterns

- Use `async/await` for all Discord operations and I/O
- Use `asyncio.Lock` for thread-safe state management
- Use `asyncio.run_coroutine_threadsafe()` for scheduling from sync callbacks
- Use `asyncio.wait_for()` with timeouts for external connections
- Use `ThreadPoolExecutor` for blocking operations (like yt-dlp)

```python
# Running blocking code in executor
loop = asyncio.get_running_loop()
info = await loop.run_in_executor(_executor, _extract_single_info, query)

# Scheduling coroutine from sync callback
asyncio.run_coroutine_threadsafe(
    self.play_next(guild_id),
    player.voice_client.loop,
)

# Thread-safe state access
async with player._lock:
    player.autoplay_queue.append(song)
```

### Design Patterns

**Singleton pattern** for global instances:
```python
player_manager = MusicPlayerManager()
```

**Lazy loading** for optional features:
```python
_game_agent = None

def get_game_agent():
    global _game_agent
    if _game_agent is None:
        from game_agent import GameAgent
        _game_agent = GameAgent()
    return _game_agent
```

**Async context manager** for resource management:
```python
async with MCPConnection(api_key) as mcp_tools:
    agent = create_game_agent(self.db, mcp_tools)
```

**Decorator pattern** for cross-cutting concerns:
```python
@log_command
async def play(interaction: discord.Interaction, query: str):
    ...
```

## Architecture Notes

### Guild-Scoped State

Each Discord server gets its own `GuildPlayer` instance stored in `MusicPlayerManager.players` dict keyed by `guild_id`.

### Key Files

| File | Purpose |
|------|---------|
| `main.py` | Bot entry point, slash command handlers |
| `music_player.py` | Per-guild player state, queue, voice connections |
| `youtube.py` | yt-dlp wrapper for audio extraction |
| `autoplay.py` | YouTube Music API for recommendations |
| `settings.py` | SQLite-backed settings management |
| `game_agent/` | AI gaming assistant package |
| `audit/` | TUI monitoring app and logging |

### Data Storage

- Settings stored in `data/settings.db` (SQLite)
- Audit logs stored in `data/audit.db` (SQLite)
- Agent memory stored in `data/agent_memory.db` (SQLite)
