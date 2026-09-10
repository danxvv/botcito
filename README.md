# Discord Music Bot

A Discord bot focused on YouTube music playback, queue controls, autoplay recommendations, and music listening stats.

## Features

- **YouTube playback** - Play songs from URLs, playlists, or search queries, with cancellable preparation and quick streaming fallback.
- **Smart autocomplete** - Song suggestions from YouTube Music while typing `/play`.
- **Autoplay** - Recommendations based on recently played songs.
- **Shared player** - One card follows each listening session with playback controls, volume, autoplay, ratings, and updated progress.
- **Queue controls** - Browse every queued song, see who requested it and its estimated waiting time, and select songs to move or remove.
- **Music stats and ratings** - Track listening history and like/dislike songs for autoplay ranking.
- **Auto-disconnect** - Leaves voice after 5 minutes of inactivity.

## Run with Docker Compose

Install Docker with the Compose plugin, then create your local configuration:

```bash
cp .env.example .env
```

Set `DISCORD_TOKEN` in `.env` (see [Bot Setup](#bot-setup)), then start the bot:

```bash
docker compose up -d
```

Compose builds the image on the first run. Python, FFmpeg, Node.js, and the locked Python dependencies are included; no local Python installation is needed. The bot restarts automatically unless you stop it. It only makes outbound connections, so no ports need to be published.

```bash
# Follow the bot's logs
docker compose logs -f bot

# Rebuild and restart after updating the code or uv.lock
docker compose up -d --build

# Open the audit TUI for the running bot
docker compose exec bot audit

# Stop the bot (keeps saved data)
docker compose down
```

Ratings and audit history are stored in the `bot-data` Docker volume mounted at `/app/data`, and survive container rebuilds and `docker compose down`. This is separate from a local checkout's `data/` directory. The audio cache uses the same directory but is cleared by the bot on startup. `docker compose down -v` deletes the volume and its saved data.

`.env`, `cookies.txt`, and local data are excluded from the image. Compose passes `DISCORD_TOKEN` at runtime and also supports `SYNC_COMMANDS=0` in `.env` to skip slash command synchronization.

## Local requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) for audio playback
- [Deno](https://deno.land), [Node.js](https://nodejs.org), or [Bun](https://bun.sh) for yt-dlp YouTube extraction
- [uv](https://docs.astral.sh/uv/) for Python dependency management

## Local installation

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

## Listening to music

1. Join a voice channel and use `/play`. Choose an autocomplete suggestion, enter a song name, or paste a YouTube URL.
2. A link containing both a video and a playlist offers **This song** and **Entire playlist**. Playlist playback starts with the first available song while the rest load; the progress message reports added and unavailable tracks.
3. Use the shared player card to pause, skip, change volume, stop, or enable autoplay. Its controls stay active throughout the session. `/nowplaying` links back to that card.
4. Use `/queue` for pages of songs and their requesters. Select a song to **Play next**, **Move**, or **Remove** it. Waiting times are approximate and are omitted while paused, preparing, or following a live stream.

Requests have a **Cancel request** button. Once a song is preparing in the player, **Cancel song** or `/skip` moves on immediately. `/clearqueue` also cancels pending imports; `/stop` cancels pending requests, clears the queue, and disconnects. Music commands are server-only, and requests from another voice channel cannot move the bot away from an existing session.

Audio already in the cache plays locally. Otherwise, the bot waits up to three seconds for the download before streaming; metadata lookup and connection time are additional. Upcoming audio is downloaded when the queue changes. Interrupted playback gets one retry from the beginning, followed by a visible skip notice if it fails again. The player card and queue belong to the running session; a bot restart starts a new session.

## Commands

| Command | Description |
|---------|-------------|
| `/play <query>` | Play a song by name, URL, or playlist URL |
| `/skip` | Skip playback or cancel the song being prepared |
| `/stop` | Cancel requests, clear queue, and disconnect |
| `/pause` | Pause the current song |
| `/resume` | Resume paused playback |
| `/queue` | Browse and edit the queue with song selections |
| `/nowplaying` | Open the shared music player |
| `/volume <percent>` | Set playback volume |
| `/remove <position>` | Remove a queued song |
| `/move <from> <to>` | Move a queued song |
| `/clearqueue` | Clear queued songs and cancel imports without stopping the current track |
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
5. Select permissions `View Channels`, `Send Messages`, `Embed Links`, `Read Message History`, `Connect`, `Speak`, and `Use Voice Activity`.
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

# Offline regression tests (no Discord connection or YouTube downloads)
uv run pytest tests/
```

Key modules:

- `main.py`: Discord client setup and slash command registration.
- `commands/music.py`: Playback and queue slash commands.
- `commands/music_requests.py`: Search selection, cancellation, and incremental playlist loading.
- `commands/player_view.py`: Shared player card and session controls.
- `commands/queue_view.py`: Paginated queue with stable song selections.
- `commands/stats.py`: Music stats and song rating commands.
- `music_player.py`: Per-guild player state, playback, autoplay, and voice connection handling.
- `youtube.py`: Async wrappers around yt-dlp extraction.
- `autoplay.py`: YouTube Music search and recommendations.
- `ratings.py`: SQLite-backed song ratings.
- `audit/`: Command and music logging plus the audit TUI.

Runtime SQLite files are created under `data/`.
