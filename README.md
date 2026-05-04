# Discord Music Bot

A Discord music bot with YouTube playback, smart autoplay recommendations, ratings, voice recording, and audit logging.

## Features

- **YouTube Playback** - Play songs from URLs, playlists, or search queries
- **Smart Autocomplete** - Real-time song suggestions as you type using YouTube Music
- **Autoplay** - Automatic song recommendations based on listening history
- **Queue Management** - Queue controls with pause, resume, skip, and stop
- **Voice Recording** - Record voice channel audio with per-user WAV files
- **Ratings** - Like or dislike tracks
- **Audit Viewer** - Inspect bot activity in a textual TUI
- **Auto-disconnect** - Bot automatically leaves after 5 minutes of inactivity

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) - Required for audio playback
- [Deno](https://deno.land) or [Node.js](https://nodejs.org) - Required by yt-dlp for YouTube extraction
- [uv](https://docs.astral.sh/uv/) - Python package manager

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/discordbotcito.git
   cd discordbotcito
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your bot token:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```

4. **Run the bot**
   ```bash
   uv run python main.py
   ```

## Commands

### Music Commands

| Command | Description |
|---------|-------------|
| `/play <query>` | Play a song by name, URL, or playlist URL |
| `/skip` | Skip the current song |
| `/stop` | Stop playback, clear queue, and disconnect |
| `/pause` | Pause the current song |
| `/resume` | Resume paused playback |
| `/queue` | Show the current queue and autoplay status |
| `/nowplaying` | Show details about the currently playing song |
| `/autoplay` | Toggle autoplay mode on/off |
| `/clearhistory` | Clear autoplay history to allow songs to repeat |

### Recording Commands

| Command | Description |
|---------|-------------|
| `/record` | Start recording voice channel audio |
| `/stoprecord` | Stop recording and save audio files |

### Rating and Stats Commands

| Command | Description |
|---------|-------------|
| `/like` | Like the currently playing song |
| `/dislike` | Dislike the currently playing song |
| `/stats` | Show listening statistics |
| `/leaderboard` | Show server listening leaderboard |

## Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to **Bot** section and create a bot
4. Enable these Privileged Gateway Intents:
   - Server Members Intent (optional)
   - Message Content Intent (optional)
5. Copy the bot token to your `.env` file
6. Go to **OAuth2 > URL Generator**:
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Connect`, `Speak`, `Use Voice Activity`
7. Use the generated URL to invite the bot to your server

## Project Structure

```text
discordbotcito/
├── main.py              # Bot entry point and command registration
├── commands/            # Slash command modules
├── music_player.py      # Per-guild player state and queue management
├── voice_recorder.py    # Voice channel recording
├── youtube.py           # yt-dlp wrapper for audio extraction
├── autoplay.py          # YouTube Music recommendations
├── ratings.py           # SQLite-backed ratings storage
├── audit/               # Command logging and TUI audit viewer
└── data/                # SQLite databases and recordings, created at runtime
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `discord.py[voice]` | Discord API and voice support |
| `discord-ext-voice-recv` | Voice receiving for recording |
| `yt-dlp` | YouTube audio extraction |
| `ytmusicapi` | YouTube Music search and recommendations |
| `textual` | Audit TUI |

## Running the Audit TUI

```bash
uv run audit
```

## License

MIT
