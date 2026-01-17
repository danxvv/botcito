# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discord music bot with slash commands, YouTube playback via Opus streaming, and autoplay functionality using YouTube Music recommendations.

## Development Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run the bot
uv run python main.py

# Or directly with python (after uv sync activates venv)
python main.py
```

## External Dependencies

The bot requires these external tools installed on the system:
- **FFmpeg** - Required for audio playback/streaming
- **Deno or Node.js** - Required by yt-dlp for YouTube JavaScript extraction

## Environment Setup

Copy `.env.example` to `.env` and add your Discord bot token:
```
DISCORD_TOKEN=your_bot_token_here
```

## Architecture

### Module Responsibilities

- **main.py** - Bot entry point, Discord client setup, slash command handlers (`/play`, `/skip`, `/stop`, `/pause`, `/resume`, `/queue`, `/nowplaying`, `/autoplay`)
- **music_player.py** - Per-guild player state management via `MusicPlayerManager`, handles queue, playback, voice connections, and auto-disconnect timer (5 min idle)
- **youtube.py** - yt-dlp wrapper for extracting audio stream URLs, supports single videos, playlists, and search; runs blocking operations in ThreadPoolExecutor
- **autoplay.py** - YouTube Music API integration via ytmusicapi for search autocomplete and song recommendations

### Key Design Patterns

**Guild-scoped state**: Each Discord server gets its own `GuildPlayer` instance (stored in `MusicPlayerManager.players` dict keyed by `guild_id`) containing voice client, queue, current song, and autoplay state.

**Async playback flow**: `MusicPlayerManager.play_next()` uses a lock to prevent race conditions. After a song finishes, FFmpeg's callback triggers the next song via `asyncio.run_coroutine_threadsafe`.

**Autocomplete**: The `/play` command uses ytmusicapi for real-time song suggestions. When user selects a suggestion, the 11-character video ID is passed directly to yt-dlp.

### Data Flow

1. User runs `/play <query>` → `search_youtube()` or `extract_song_info()` gets stream URL
2. Song added to guild's queue via `player_manager.add_to_queue()`
3. `play_next()` creates `FFmpegOpusAudio` source from stream URL and plays via voice client
4. On song end, callback triggers `play_next()` again
5. If queue empty and autoplay enabled, `_get_autoplay_song()` fetches recommendations from YouTube Music
