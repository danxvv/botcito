# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Discord music bot with slash commands, YouTube playback via Opus streaming, autoplay functionality using YouTube Music recommendations, voice channel recording, ratings, and audit logging.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the bot
uv run python main.py

# Run the audit TUI
uv run audit

# Quick syntax check
uv run python -m compileall .
```

## External Dependencies

The bot requires these external tools installed on the system:
- **FFmpeg** - Required for audio playback/streaming
- **Deno or Node.js** - Required by yt-dlp for YouTube JavaScript extraction

## Environment Setup

Copy `.env.example` to `.env` and configure:

```env
DISCORD_TOKEN=your_bot_token_here
```

## Architecture

### Module Responsibilities

- **main.py** - Bot entry point, Discord client setup, command registration, and dependency checks.
- **commands/** - Slash command modules for music playback, stats, and recording.
- **music_player.py** - Per-guild player state management via `MusicPlayerManager`; handles queue, playback, voice connections, recordings, and auto-disconnect.
- **youtube.py** - yt-dlp wrapper for extracting audio stream URLs; supports single videos, playlists, and search.
- **autoplay.py** - YouTube Music API integration via ytmusicapi for autocomplete and song recommendations.
- **ratings.py** - SQLite-backed like/dislike storage.
- **audit/** - Command and music event logging plus textual TUI viewer.

### Key Design Patterns

**Guild-scoped state**: Each Discord server gets its own `GuildPlayer` instance stored in `MusicPlayerManager.players`, keyed by `guild_id`.

**Async playback flow**: `MusicPlayerManager.play_next()` uses a lock to prevent race conditions. After a song finishes, FFmpeg's callback triggers the next song via `asyncio.run_coroutine_threadsafe`.

**Autocomplete**: The `/play` command uses ytmusicapi for real-time song suggestions. When a user selects a suggestion, the 11-character video ID is passed directly to yt-dlp.

### Data Flow

1. User runs `/play <query>`.
2. `youtube.py` extracts stream metadata via yt-dlp.
3. Song is added to the guild queue with `player_manager.add_to_queue()`.
4. `play_next()` creates an FFmpeg audio source and starts playback.
5. On song end, callback triggers `play_next()` again.
6. If the queue is empty and autoplay is enabled, `_get_autoplay_song()` fetches recommendations from YouTube Music.
