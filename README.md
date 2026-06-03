# Discord Music Bot

A Discord bot focused on YouTube music playback, queue controls, autoplay recommendations, and music listening stats.

## Features

- **YouTube playback** - Play songs from URLs, playlists, or search queries.
- **Smart autocomplete** - Song suggestions from YouTube Music while typing `/play`.
- **Autoplay** - Recommendations based on recently played songs.
- **Queue controls** - Pause, resume, skip, stop, shuffle, volume, queue editing, and now-playing controls.
- **Music stats and ratings** - Track listening history and like/dislike songs for autoplay ranking.
- **Auto-disconnect** - Leaves voice after 5 minutes of inactivity.

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) for audio playback
- [Deno](https://deno.land), [Node.js](https://nodejs.org), or [Bun](https://bun.sh) for yt-dlp YouTube extraction
- [uv](https://docs.astral.sh/uv/) for Python dependency management

## Installation

```bash
git clone https://github.com/yourusername/discordbotcito.git
cd discordbotcito
uv sync
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your_bot_token_here
```

Run the bot:

```bash
uv run python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/play <query>` | Play a song by name, URL, or playlist URL |
| `/skip` | Skip the current song |
| `/stop` | Stop playback, clear queue, and disconnect |
| `/pause` | Pause the current song |
| `/resume` | Resume paused playback |
| `/queue` | Show the current queue and autoplay status |
| `/nowplaying` | Show details about the currently playing song |
| `/volume <percent>` | Set playback volume |
| `/remove <position>` | Remove a queued song |
| `/move <from> <to>` | Move a queued song |
| `/clearqueue` | Clear queued songs without stopping playback |
| `/history` | Show recently played songs |
| `/replay [position]` | Replay a song from recent history |
| `/autoplay [action]` | Toggle, inspect, or refresh autoplay |
| `/clearhistory` | Clear autoplay history |
| `/shuffle` | Shuffle the current queue |
| `/stats` | View your music listening statistics |
| `/leaderboard` | View the server music leaderboard |
| `/like` | Like the current song |
| `/dislike` | Dislike the current song |
| `/unrate` | Remove your rating for the current song |
| `/favorites` | Show your liked songs |

## Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application and bot.
3. Copy the bot token into `.env`.
4. In **OAuth2 > URL Generator**, select scopes `bot` and `applications.commands`.
5. Select permissions `Connect`, `Speak`, and `Use Voice Activity`.
6. Use the generated URL to invite the bot to your server.

## Developer Notes

```bash
# Install/update dependencies
uv sync

# Run the bot
uv run python main.py

# Run the audit TUI
uv run audit

# Syntax check
uv run python -m compileall main.py commands audit audio_cache.py autoplay.py music_player.py ratings.py youtube.py
```

Key modules:

- `main.py`: Discord client setup and slash command registration.
- `commands/music.py`: Playback and queue slash commands.
- `commands/stats.py`: Music stats and song rating commands.
- `music_player.py`: Per-guild player state, playback, autoplay, and voice connection handling.
- `youtube.py`: Async wrappers around yt-dlp extraction.
- `autoplay.py`: YouTube Music search and recommendations.
- `ratings.py`: SQLite-backed song ratings.
- `audit/`: Command and music logging plus the audit TUI.

Runtime SQLite files are created under `data/`.
