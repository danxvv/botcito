# Discord Music Bot

A feature-rich Discord music bot with YouTube playback, smart autoplay recommendations, and an AI-powered gaming assistant.

## Features

- **YouTube Playback** - Play songs from URLs, playlists, or search queries
- **Smart Autocomplete** - Real-time song suggestions as you type using YouTube Music
- **Autoplay** - Automatic song recommendations based on your listening history
- **Queue Management** - Full queue controls with pause, resume, skip, and stop
- **Voice Recording** - Record voice channel audio with per-user WAV files
- **Voice Conversation** - Talk to the AI assistant using voice (requires TTS provider)
- **AI Gaming Assistant** - Get help with game strategies, builds, and tips using web search
- **Auto-disconnect** - Bot automatically leaves after 5 minutes of inactivity

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) - Required for audio playback
- [Deno](https://deno.land) or [Node.js](https://nodejs.org) - Required by yt-dlp for YouTube extraction
- [uv](https://docs.astral.sh/uv/) - Python package manager (recommended)

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

   Edit `.env` with your credentials:
   ```
   DISCORD_TOKEN=your_bot_token_here

   # Optional - for /guide command
   EXA_API_KEY=your_exa_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key

   # TTS provider (default: local Qwen3-TTS)
   TTS_PROVIDER=qwen
   TTS_SETTINGS_PATH=data/tts_settings.json

   # Optional Chatterbox MCP config
   TTS_MCP_URL=http://127.0.0.1:8080/mcp
   TTS_DEFAULT_LANGUAGE=es
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

### Voice Conversation Commands

| Command | Description |
|---------|-------------|
| `/talk` | Start voice conversation mode - bot listens and responds |
| `/stoptalk` | Stop voice conversation mode |
| `/speak <text>` | Make the bot speak text aloud |

> **Note:** Qwen3-TTS is the default local provider. Chatterbox MCP is still available by setting `TTS_PROVIDER=chatterbox`.

### AI Commands

| Command | Description |
|---------|-------------|
| `/guide <question>` | Ask the AI gaming assistant for help |
| `/model <model>` | Change the AI model used by /guide |

**Available AI Models:**
- OpenAI GPT-5.2
- xAI Grok 4.1 Fast
- Google Gemini 3 Pro / Flash
- Anthropic Claude Sonnet 4.5 / Haiku 4.5

## Qwen3-TTS Configuration (Default)

- Default provider: `TTS_PROVIDER=qwen`
- Runtime settings file: `data/tts_settings.json` (auto-created on first TTS use)
- Example settings template: `tts_settings.example.json`
- CUDA GPU is required for local Qwen TTS inference

`data/tts_settings.json` supports two modes:
- `custom_voice`: uses `Qwen/Qwen3-TTS-0.6B` with built-in speaker voices
- `base_clone`: uses `Qwen/Qwen3-TTS-0.6B-Base` with `reference_audio_path` + `reference_text`

To use Chatterbox instead:
- Set `TTS_PROVIDER=chatterbox`
- Ensure the MCP server is running and `TTS_MCP_URL` is configured

## Bot Setup (Discord Developer Portal)

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

---

## Developer Documentation

### Project Structure

```
discordbotcito/
├── main.py              # Bot entry point, slash command handlers
├── music_player.py      # Per-guild player state and queue management
├── voice_recorder.py    # Voice channel recording (per-user WAV files)
├── youtube.py           # yt-dlp wrapper for audio extraction
├── autoplay.py          # YouTube Music API for recommendations
├── settings.py          # SQLite-backed settings storage
├── tts_settings.example.json  # Example Qwen TTS settings template
├── game_agent/          # AI gaming assistant package
│   ├── agent.py         # Main GameAgent class
│   ├── mcp_client.py    # MCP tools connection
│   ├── session.py       # Per-user session context
│   ├── config.py        # Agent instructions and paths
│   └── environment.py   # Environment validation
├── voice_agent/         # Voice conversation package
│   ├── listener.py      # Voice activity detection and audio capture
│   ├── conversation.py  # Listen → AI → Speak orchestrator
│   ├── tts.py           # Text-to-speech abstraction layer
│   └── qwen3_tts.py     # Local Qwen3-TTS provider with JSON settings
├── audit/               # Command logging and TUI audit viewer
└── data/                # SQLite databases and recordings (created at runtime)
```

### Architecture

#### Guild-Scoped State
Each Discord server gets its own `GuildPlayer` instance stored in `MusicPlayerManager.players`, containing:
- Voice client connection
- Song queue and autoplay queue
- Current song and playback state
- Listening history for recommendations

#### Async Playback Flow
1. User runs `/play <query>`
2. `youtube.py` extracts audio stream URL via yt-dlp
3. Song added to guild's queue
4. `MusicPlayerManager.play_next()` creates FFmpeg audio source
5. On song end, callback triggers next song
6. If queue empty and autoplay enabled, fetches recommendations from YouTube Music

#### Autoplay System
- Uses `ytmusicapi` to get song recommendations
- Tracks recently played songs to avoid repetition
- Pre-fetches 3 songs ahead for seamless playback
- Blends recommendations from multiple recent songs

#### AI Gaming Assistant
- Built with [Agno](https://github.com/agno-ai/agno) framework
- Uses [Exa](https://exa.ai) MCP server for web search
- Per-user memory isolation via SQLite
- Streams responses with real-time Discord embed updates

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `discord.py[voice]` | Discord API and voice support |
| `discord-ext-voice-recv` | Voice receiving for recording and conversation |
| `yt-dlp` | YouTube audio extraction |
| `ytmusicapi` | YouTube Music search and recommendations |
| `agno` | AI agent framework |
| `mcp` | Model Context Protocol for AI tools |
| `sqlalchemy` | Database ORM |
| `qwen-tts` | Local Qwen3 text-to-speech inference |

### Running the Audit TUI

```bash
uv run audit
```

## License

MIT
