# botcito

**Music for your Discord server, one `/play` away.**

botcito is a Discord music bot you host yourself. Play songs and playlists from YouTube, build a queue with friends, and let autoplay keep the music going. Shared player controls, song ratings, and listening stats live right in Discord.

[Get started](#get-started) · [Listen together](#listen-together) · [Commands](#commands) · [Troubleshooting](#troubleshooting) · [Contributing](#contributing)

## What you can do

- **Find a song quickly.** Search by name, choose a YouTube Music autocomplete suggestion, or paste a YouTube link.
- **Bring a whole playlist.** The queue fills instantly and music starts right away; each track is prepared as its turn comes, with progress updates and a cancel button.
- **Share the controls.** Pause, skip, change volume, rate songs, and toggle autoplay from a player card that updates during the session.
- **Make the queue your own.** Browse songs and requesters, move a track up next, remove entries, or shuffle the queue.
- **Discover more music.** Autoplay recommends songs using recent plays and likes/dislikes.
- **See your listening history.** Replay recent tracks, find your liked songs, and check personal stats or the server leaderboard.

## Get started

You'll need a Discord server where you can add bots and a computer or server that stays on while botcito runs. Docker Compose includes Python, FFmpeg, Node.js, and the Python dependencies for you. Prefer running directly on your machine? Follow [Run locally](#run-locally) after creating your Discord bot.

### 1. Create your Discord bot

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Open **Bot**, generate a token, and save it for the next step.
3. Under **Installation**, enable **Guild Install** and select **Discord Provided Link**.
4. In **Default Install Settings → Guild Install**, select the `bot` and `applications.commands` scopes.
5. Add these permissions: **View Channels**, **Send Messages**, **Embed Links**, **Read Message History**, **Connect**, **Speak**, and **Use Voice Activity**.
6. Open the install link, choose **Add to server**, and select your server.

Discord's [bot setup guide](https://docs.discord.com/developers/quick-start/getting-started) explains the portal settings in more detail. Keep your token in your local `.env` file; never include it in a commit or issue.

### 2. Download and configure botcito

With Git and Docker Compose installed, run:

```bash
git clone https://github.com/danxvv/botcito.git
cd botcito
cp .env.example .env
```

Open `.env` and replace the placeholder with your bot token:

```env
DISCORD_TOKEN=your_bot_token_here
```

### 3. Start the bot

```bash
docker compose up -d --build
docker compose logs -f bot
```

Wait for `Logged in as ...` in the logs. Press **Ctrl+C** to stop following logs; the bot keeps running in the background. It restarts automatically unless you stop it, and no ports need to be published.

Join a Discord voice channel, then type `/play` in a text channel and enter a song name in the `query` field. You're ready to listen.

## Listen together

1. **Add music:** use `/play` with a song name, YouTube video, or playlist URL. A link containing both a video and a playlist lets you choose **This song** or **Entire playlist**.
2. **Control playback:** use the shared player card for pause/resume, skip, volume, ratings, and autoplay. `/nowplaying` takes you back to it.
3. **Arrange the queue:** run `/queue`, select a song, then choose **Play next**, **Move**, or **Remove**. Pages show who requested each song and an estimated wait when available.
4. **Keep it going:** enable `/autoplay` for recommendations when your queue runs out. Like or dislike the current song to influence future recommendations.
5. **Finish the session:** `/stop` cancels pending requests, clears the queue, and disconnects. The bot also leaves after five minutes of inactivity, or one minute after the last person leaves its voice channel (even with autoplay on).

Changed your mind? Use **Cancel request** while a search or playlist is loading, or **Cancel song** / `/skip` while a track is preparing. `/clearqueue` cancels pending imports and clears upcoming songs while the current track keeps playing.

Playback commands work in server channels. Join the bot's voice channel to control an active session; requests from another voice channel cannot move it away.

## Commands

In the tables below, `<...>` means required and `[...]` means optional. Discord displays these as command fields.

### Playback

| Command | What it does |
| --- | --- |
| `/play <query>` | Play or queue a song, search result, or YouTube playlist |
| `/nowplaying` | Open the shared player card |
| `/pause` | Pause the current song |
| `/resume` | Resume playback |
| `/skip` | Skip the current song or cancel its preparation |
| `/seek <position>` | Jump to a time in the current song: `1:30`, `90` (seconds), or `+30` / `-15` from now |
| `/volume <percent>` | Set the volume from 0 to 100 |
| `/stop` | Cancel requests, clear the queue, and disconnect |

### Queue and discovery

| Command | What it does |
| --- | --- |
| `/queue` | Browse and edit the queue |
| `/remove <position>` | Remove a queued song by its position |
| `/move <from_position> <to_position>` | Move a song to another queue position |
| `/shuffle` | Shuffle upcoming songs |
| `/clearqueue` | Clear upcoming songs and cancel pending imports |
| `/history` | Show recently played songs |
| `/replay [position]` | Queue a song from `/history`; defaults to position 1 |
| `/autoplay [action]` | Toggle autoplay, check its status, or refresh recommendations |
| `/clearhistory` | Reset autoplay's recent-song history so songs can repeat |

### Ratings and stats

| Command | What it does |
| --- | --- |
| `/like` | Like the current song |
| `/dislike` | Dislike the current song |
| `/unrate` | Remove your rating for the current song |
| `/favorites` | Show your recently liked songs |
| `/stats [period]` | View your listening statistics |
| `/leaderboard [period]` | View the server's music leaderboard |

Stats and leaderboard periods are **Last 24 hours**, **Last 7 days**, **Last 30 days**, or **All time** (the default).

## Run locally

Install [uv](https://docs.astral.sh/uv/), [FFmpeg](https://ffmpeg.org/download.html), and one JavaScript runtime: [Deno](https://deno.land), [Node.js](https://nodejs.org), or [Bun](https://bun.sh). Python 3.10+ is supported; the checkout pins Python 3.13.13 in `.python-version`, which `uv` can provision.

After [creating your Discord bot](#1-create-your-discord-bot), clone and configure the project if you haven't already:

```bash
git clone https://github.com/danxvv/botcito.git
cd botcito
cp .env.example .env
uv sync
```

Set `DISCORD_TOKEN` in `.env`, then start the bot:

```bash
uv run python main.py
```

Keep this process running while you use the bot. Press **Ctrl+C** to stop it.

## Configuration and maintenance

| Variable | Required? | Purpose |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | The token from your application's **Bot** page |
| `SYNC_COMMANDS` | No | Defaults to `1`; set to `0` to skip slash command synchronization on startup |
| `LOG_LEVEL` | No | Defaults to `INFO`; use `DEBUG` to include yt-dlp's detailed extraction output |

Run these commands from the project folder:

```bash
# Update a Docker installation
git pull --ff-only
docker compose up -d --build

# Follow logs
docker compose logs -f bot

# Check the container's health (the bot refreshes a heartbeat while connected to Discord)
docker compose ps

# Open the audit viewer in your terminal
docker compose exec bot audit

# Stop the bot and keep saved data
docker compose down
```

For a local installation, stop the bot, run `git pull --ff-only` and `uv sync`, then start it again. Open the local audit viewer with `uv run audit`.

### What gets saved?

Ratings and audit history use SQLite databases (`ratings.db` and `audit.db`). Local runs save them under `data/`; Docker stores them in the `bot-data` volume at `/app/data`, separately from the local folder.

Docker rebuilds and `docker compose down` preserve saved data. **`docker compose down -v` deletes the volume and its saved data.** The audio cache is temporary and cleared on startup. Queues and player cards belong to the running session, so restarting the bot starts a new session.

### Playback details

Cached audio plays locally. Otherwise, the bot waits up to three seconds for a download before falling back to streaming; searching and connecting may take additional time. It also downloads upcoming tracks in advance. Interrupted playback gets one retry from where it stopped, then a visible skip notice if it fails again. Playlist tracks are looked up just before they are needed; a track that turns out to be private or removed is skipped with a notice. Autoplay avoids songs your server disliked, and songs that people keep skipping rank lower. If autoplay runs out of unplayed recommendations, it mixes earlier songs back in rather than stopping.

Links to YouTube and to sites with their own yt-dlp support can be played. Links to arbitrary web pages or direct file URLs are rejected, so the bot cannot be pointed at addresses on your network.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| The bot is offline | Check the logs and confirm `.env` contains a valid `DISCORD_TOKEN`. For local runs, keep the terminal process running. |
| Slash commands are missing | Confirm the bot was installed with `applications.commands`, leave `SYNC_COMMANDS` at `1`, and check startup logs for sync errors. |
| The bot cannot join or speak | Join a voice channel and check its **Connect** and **Speak** permissions, including channel overrides. |
| The player card cannot appear | Check **View Channels**, **Send Messages**, and **Embed Links** in the text channel. |
| A song fails to play | Try another public YouTube video and check the logs. For local runs, verify FFmpeg and a supported JavaScript runtime are on your `PATH`. |
| Many songs fail at once | YouTube changes often, and an old yt-dlp is the usual cause. The startup log warns when yt-dlp is more than 45 days old. Run `uv lock --upgrade-package yt-dlp`, then rebuild with `docker compose up -d --build` (or run `uv sync` locally). |
| Controls belong to an old session | Run `/play` to start a session, then `/nowplaying` to open its player card. |

Still stuck? [Open an issue](https://github.com/danxvv/botcito/issues) with what you tried, your setup (Docker or local), and relevant logs with tokens and private information removed.

## Contributing

Bug reports, documentation improvements, tests, and code contributions are welcome. For a larger feature, open an issue first so we can agree on the scope.

### Make your first change

1. Fork this repository, clone your fork, and create a branch for your change.
2. Run `uv sync` to install the project and development dependencies.
3. Make a focused change and follow the conventions in [AGENTS.md](AGENTS.md): readable Python, type hints for new or updated functions, and small, purposeful helpers.
4. Run the checks below. Add or update offline regression tests when changing behavior, and update the README when setup or commands change.
5. Push your branch and open a pull request against `master`. Explain the problem, what changed, and how you verified it. Include screenshots for Discord interface changes when useful.

```bash
# Run from the repository root
uv run pytest tests/
uv run python -m compileall main.py commands audit audio_cache.py autoplay.py background.py health.py music_player.py ratings.py youtube.py

# Run just the playback tests while working on that area
uv run pytest tests/test_playback.py -v
```

The regression suite uses fake voice clients and mocked extraction, so tests need no Discord token, live Discord connection, or YouTube downloads. GitHub Actions runs it on Python 3.10 and 3.13 and checks that the Docker image builds. When you add a top-level module, list it in `pyproject.toml` (`py-modules`) and `.dockerignore`; `tests/test_packaging.py` fails if either is missing. To try the bot itself, follow [Run locally](#run-locally) with your own bot and test server. Keep `.env`, `cookies.txt`, and runtime data out of commits.

### Find your way around

| Path | Responsibility |
| --- | --- |
| `main.py` | Bot startup and slash command registration |
| `commands/music.py` | Playback and queue commands |
| `commands/music_requests.py` | Search selection, cancellation, and playlist loading |
| `commands/player_view.py`, `commands/queue_view.py` | Interactive player and queue controls |
| `commands/stats.py` | Stats, leaderboard, and song ratings |
| `music_player.py` | Per-server state, playback, autoplay, and voice connections |
| `youtube.py`, `audio_cache.py` | YouTube extraction and audio caching |
| `background.py` | Fire-and-forget tasks that stay referenced and log failures |
| `health.py` | Heartbeat file for the container health check, and the yt-dlp age check |
| `autoplay.py`, `ratings.py` | Recommendations and saved ratings |
| `audit/` | Event logging, database, and terminal viewer |
| `tests/` | Offline regression tests |
