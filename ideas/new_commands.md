# New Commands & Features Research

> Research document for expanding the Discord music bot with new slash commands, interactive UI components, and quality-of-life features. Each idea includes a description, user value, discord.py feasibility notes, and complexity estimate.

---

## Current Bot Capabilities (Reference)

| Category | Commands |
|----------|----------|
| Music | `/play`, `/skip`, `/stop`, `/pause`, `/resume`, `/queue`, `/nowplaying`, `/autoplay`, `/clearhistory`, `/shuffle` |
| Ratings | `/like`, `/dislike` |
| Stats | `/stats`, `/leaderboard` |
| Recording | `/record`, `/stoprecord` |
| Voice/TTS | `/talk`, `/stoptalk`, `/speak` |
| AI | `/guide`, `/model` |

The bot uses discord.py 2.6+, guild-scoped `GuildPlayer` state, FFmpeg+Opus streaming, yt-dlp for YouTube, ytmusicapi for autocomplete and recommendations, and an Agno-based game agent with Exa MCP for web search.

---

## 1. Music Control & Queue Management

### `/seek <timestamp>`
**Description:** Jump to a specific timestamp in the currently playing song (e.g., `/seek 1:30` or `/seek 90`).

**User Value:** Lets users skip intros, replay a specific part, or jump to the drop without restarting the entire song. Essential for longer tracks, mixes, and podcasts.

**discord.py Feasibility:** Requires restarting FFmpegPCMAudio with `-ss <seconds>` as a before_option. The existing `_create_audio_source` method in `MusicPlayerManager` already supports custom FFmpeg options. Timestamp parsing is straightforward string logic.

**Complexity:** Medium -- Need to stop current source, recalculate with a new FFmpeg `-ss` offset, update `song_start_time` accounting, and handle edge cases (seeking past end, seeking in live streams).

---

### `/loop [mode]`
**Description:** Cycle through loop modes: off -> single song -> entire queue -> off. When looping a single song, it replays when finished. When looping the queue, finished songs get re-appended.

**User Value:** One of the most requested features in any music bot. Users want to replay favorites or keep a playlist going indefinitely without autoplay's randomness.

**discord.py Feasibility:** Pure application logic. Add a `loop_mode` enum field to `GuildPlayer` and modify the `after_callback` / `play_next` flow to either re-queue the current song or re-append finished songs.

**Complexity:** Low -- Mainly state management in `GuildPlayer` and branching in `play_next()`.

---

### `/remove <position>`
**Description:** Remove a specific song from the queue by its position number (as shown in `/queue`).

**User Value:** Lets users fix mistakes (accidentally queued wrong song) or remove unwanted songs that someone else added, without clearing the whole queue.

**discord.py Feasibility:** Trivial. The queue is a `deque[SongInfo]` -- index and remove. Add autocomplete showing queue entries for better UX.

**Complexity:** Low -- Index into `player.queue`, validate bounds, pop the item.

---

### `/move <from> <to>`
**Description:** Move a song from one position to another in the queue.

**User Value:** Lets users reorder the queue without removing and re-adding songs. Great for collaborative listening sessions where the group wants to bump a song up.

**discord.py Feasibility:** Same as `/remove` -- manipulate the `deque`. No UI components needed, just two integer parameters.

**Complexity:** Low -- Pop from index, insert at index.

---

### `/volume <level>`
**Description:** Set the playback volume (0-100%). The bot already has `PCMVolumeTransformer` and `set_volume`/`get_volume` methods -- this just exposes them as a command.

**User Value:** Users often want to lower volume for background music or boost it for party mode. Currently only accessible programmatically.

**discord.py Feasibility:** Already implemented in `MusicPlayerManager` (`set_volume`, `get_volume`, `PCMVolumeTransformer`). Just needs a slash command wrapper.

**Complexity:** Very Low -- Literally wrapping an existing method.

---

### `/replay`
**Description:** Restart the currently playing song from the beginning.

**User Value:** Quick way to replay without searching for it again. Simpler than `/seek 0`.

**discord.py Feasibility:** Stop current playback and re-queue the same `SongInfo` at the front, or restart FFmpeg with `-ss 0`.

**Complexity:** Low -- Re-use existing `play_next` logic with the current song re-inserted.

---

### `/skipto <position>`
**Description:** Skip directly to a specific song in the queue, removing everything before it.

**User Value:** When a queue has built up and users want to jump ahead to a specific song without manually skipping one by one.

**discord.py Feasibility:** Pop items from the front of the deque until reaching the target position, then trigger `play_next`.

**Complexity:** Low -- Queue manipulation plus one `skip()` call.

---

### `/lyrics`
**Description:** Fetch and display lyrics for the currently playing song. Use a lyrics API (Genius, Musixmatch, or lrclib) to find matching lyrics.

**User Value:** One of the most popular features in music bots. Users want to sing along or check lyrics without leaving Discord.

**discord.py Feasibility:** Lyrics are often too long for a single embed (4096 char limit). Use a **paginated View with buttons** (Previous/Next) to flip through lyric pages. discord.py `ui.View` with `ui.Button` handles this perfectly. Could also use ephemeral responses to avoid channel spam.

**Complexity:** Medium -- Need an external lyrics API integration, text pagination logic, and a button-based View for navigation.

---

### `/radio <genre|mood|artist>`
**Description:** Start a continuous radio mode that plays songs based on a genre, mood, or artist seed. Different from autoplay (which is based on the last played song) -- radio maintains a consistent theme.

**User Value:** "Play jazz radio" or "play chill vibes" without needing to find specific songs. Great for background music sessions.

**discord.py Feasibility:** Leverage ytmusicapi to search by genre/mood and feed results into the autoplay queue. Could use `ui.Select` dropdown for genre/mood selection, or autocomplete for artist names.

**Complexity:** Medium -- Requires a new recommendation strategy separate from the existing autoplay logic, plus a way to maintain the radio "seed" concept across song transitions.

---

## 2. Playlist & Favorites System

### `/playlist save <name>`
**Description:** Save the current queue (including the now-playing song) as a named playlist stored per-guild or per-user.

**User Value:** Users can curate and reuse playlists without re-queuing songs every session. Essential for recurring listening sessions (e.g., "Friday Night" playlist, "Workout" playlist).

**discord.py Feasibility:** Store in SQLite (the bot already uses SQLite for settings and ratings). Schema: `playlists(id, guild_id, user_id, name, created_at)` and `playlist_songs(playlist_id, position, video_id, title, duration)`.

**Complexity:** Medium -- Database schema, CRUD operations, and new commands.

---

### `/playlist load <name>`
**Description:** Load a saved playlist into the queue. Autocomplete shows available playlists.

**User Value:** One-command restoration of a curated playlist. Combined with `/shuffle`, this covers most use cases.

**discord.py Feasibility:** Use autocomplete to show the user's saved playlists. Re-extract song info for each video ID (URLs may have expired).

**Complexity:** Medium -- Autocomplete integration, bulk song extraction (may be slow for large playlists).

---

### `/playlist list`
**Description:** Show all saved playlists for the current server/user with song counts and total duration.

**User Value:** Browse available playlists before loading one.

**discord.py Feasibility:** Simple embed response. Could use paginated view for many playlists.

**Complexity:** Low -- Database query and embed formatting.

---

### `/playlist delete <name>`
**Description:** Delete a saved playlist. Only the creator or server admins can delete.

**User Value:** Cleanup old playlists.

**discord.py Feasibility:** Permission check via `interaction.user.guild_permissions.administrator` or matching `user_id`. Use autocomplete for playlist names.

**Complexity:** Low -- Database delete with permission check.

---

### `/favorites add`
**Description:** Add the currently playing song to your personal favorites list (cross-server).

**User Value:** Personal music library that follows the user across servers. Quick save without creating a named playlist.

**discord.py Feasibility:** Store in SQLite keyed by `user_id` (not `guild_id`). Simple insert.

**Complexity:** Low -- Single table, simple CRUD.

---

### `/favorites list`
**Description:** Show your favorite songs with a paginated embed view.

**User Value:** Browse and manage your saved songs.

**discord.py Feasibility:** Paginated `ui.View` with Previous/Next buttons. Each page shows 10 songs.

**Complexity:** Low-Medium -- Pagination view, database query.

---

### `/favorites play`
**Description:** Queue all your favorite songs (optionally shuffled).

**User Value:** Instant personal playlist without manual setup.

**discord.py Feasibility:** Iterate favorites, extract song info, add to queue. Option to shuffle via a boolean parameter.

**Complexity:** Medium -- Bulk song extraction, queue insertion.

---

## 3. Social & Interactive Features

### `/poll <question> [option1] [option2] ...`
**Description:** Create a poll with buttons for voting. Great for "what should we listen to next?" scenarios.

**User Value:** Democratic song selection, or general-purpose polls during listening sessions.

**discord.py Feasibility:** Excellent fit for `ui.View` with `ui.Button` components. Each option gets a button. Track votes in memory (dict keyed by user ID to prevent double-voting). Show results in an updated embed when the poll ends (timeout or manual close).

**Complexity:** Medium -- View with dynamic buttons, vote tracking, result calculation, timeout handling.

---

### `/songpoll`
**Description:** Automatically create a poll from the next N songs in the queue. Users vote on which to play next. The winner gets moved to position 1.

**User Value:** Collaborative queue management. The group decides what plays next instead of one person controlling the queue.

**discord.py Feasibility:** Generate buttons from queue items. On timeout/completion, reorder queue based on votes. Uses `ui.View` with buttons.

**Complexity:** Medium -- Combines poll logic with queue manipulation.

---

### `/share`
**Description:** Share the currently playing song as a formatted embed with a YouTube link, thumbnail, and "Add to Queue" button that others can click.

**User Value:** Easy song sharing. The button lets others queue the song in one click without needing to copy-paste URLs.

**discord.py Feasibility:** Send an embed with a `ui.Button` labeled "Add to Queue". The button callback runs the same logic as `/play` with the video URL. Use `custom_id` with the video ID embedded for persistent buttons.

**Complexity:** Medium -- Persistent button view, callback that triggers play logic.

---

### `/dj <role|user>`
**Description:** Restrict music commands to users with a specific role or specific users. Creates a "DJ mode" where only authorized users can add/skip/stop songs.

**User Value:** Prevents queue trolling in larger servers. Gives server admins control over who can manage music.

**discord.py Feasibility:** Store DJ role/users in SQLite per guild. Add an `interaction_check` or decorator to music commands that verifies the user has DJ permissions. Use `app_commands.checks.has_role()` or custom check.

**Complexity:** Medium -- Permission system, settings storage, check decorator applied to multiple commands.

---

### `/notify <song_title|artist>`
**Description:** Get a DM notification when a specific song or artist starts playing in the server.

**User Value:** "Let me know when my favorite song comes on" -- useful in servers with active music sessions.

**discord.py Feasibility:** Store notification subscriptions in SQLite. In `play_next`, check if the new song matches any subscriptions and send DMs via `user.send()`. Need to handle DM permissions (some users block bot DMs).

**Complexity:** Medium -- Subscription storage, matching logic in play_next, DM sending with error handling.

---

### `/collab [on|off]`
**Description:** Toggle collaborative mode where all users in the voice channel can interact with the queue via buttons on the now-playing embed. Shows real-time "who added what" tracking.

**User Value:** Makes the bot feel more social. Everyone can see who added songs and interact without typing commands.

**discord.py Feasibility:** Use a persistent `ui.View` attached to the now-playing message with Skip/Pause/Resume buttons. Track who added each song in a dict on `SongInfo`. Update the embed on each song change.

**Complexity:** High -- Persistent interactive embeds that update across song transitions, user attribution tracking.

---

## 4. Games & Entertainment

### `/trivia [genre]`
**Description:** Music trivia game. The bot plays a snippet of a song (first 15-30 seconds) and users guess the title or artist. Uses buttons for multiple-choice answers.

**User Value:** Highly engaging interactive game that leverages the bot's music capabilities. Great for server entertainment and community building.

**discord.py Feasibility:** Combine audio playback (existing FFmpeg infrastructure with `-t 30` to limit duration) with a `ui.View` containing 4 `ui.Button` choices. Track scores in memory or SQLite. Use `on_timeout` to reveal the answer.

**Complexity:** High -- Song selection logic, audio snippet playback, timed game rounds, score tracking, button-based answer UI.

---

### `/quiz`
**Description:** A simpler text-based music quiz. The bot shows lyrics or song descriptions and users guess the song. No audio playback needed.

**User Value:** Fun text-based alternative to trivia that works even without voice channel. Can be played asynchronously.

**discord.py Feasibility:** Embed with clue text + `ui.Button` answers or `ui.Modal` for free-text answers. Lyrics API for clue generation.

**Complexity:** Medium -- Question generation, answer validation, scoring.

---

### `/8ball <question>`
**Description:** Classic Magic 8-Ball. Ask a question, get a random mystical answer.

**User Value:** Simple, fun social command that encourages interaction. Very low effort, high engagement.

**discord.py Feasibility:** Trivial. Random choice from a list of responses. Formatted embed with a dark theme.

**Complexity:** Very Low -- One random.choice call and an embed.

---

### `/coinflip`
**Description:** Flip a coin. Optionally mention a user to "flip against" them.

**User Value:** Quick decision maker. Useful for "who picks the next song" scenarios.

**discord.py Feasibility:** Trivial. Random choice, embed with result.

**Complexity:** Very Low.

---

## 5. Productivity & Utility

### `/timer <minutes> [message]`
**Description:** Set a timer that notifies the channel when it expires. Optionally plays a sound effect through voice.

**User Value:** Study/work timer, break reminders, or game session time limits. Pairs well with background music.

**discord.py Feasibility:** Use `asyncio.sleep()` for the timer. Send a message and optionally play a sound file via the existing `play_audio_file` method. Show countdown via an updating embed.

**Complexity:** Low-Medium -- Timer task management, optional audio notification.

---

### `/pomodoro [work_minutes] [break_minutes]`
**Description:** Start a Pomodoro session. Alternates between work (25min default) and break (5min default) periods. Optionally plays different music during work vs break, or pauses music during work.

**User Value:** Productivity tool that integrates with the music experience. "Focus mode with my favorite study playlist."

**discord.py Feasibility:** State machine with `asyncio.sleep()` for intervals. Use `ui.View` with Start/Pause/Stop buttons. Update an embed showing current phase and time remaining. Could integrate with existing play/pause commands.

**Complexity:** High -- Multi-phase timer, state management, interactive buttons, optional music integration.

---

### `/schedule <time> <action> [args]`
**Description:** Schedule a bot action at a specific time. Examples: `/schedule 20:00 play lofi hip hop`, `/schedule 18:00 stop`.

**User Value:** Automate the bot for recurring events. "Start playing music when our game night starts at 8pm."

**discord.py Feasibility:** Parse time strings, store scheduled tasks in SQLite, run a background check loop with `discord.ext.tasks.loop`. Execute the corresponding command logic at the scheduled time.

**Complexity:** High -- Time parsing, persistent storage, background task loop, command dispatch.

---

## 6. Audio & Sound Effects

### `/soundboard <sound_name>`
**Description:** Play short sound effects (airhorn, rimshot, sad trombone, etc.) from a pre-configured library of audio files. Interrupts briefly then resumes music.

**User Value:** Fun social feature for reactions during conversations. Adds personality to voice sessions.

**discord.py Feasibility:** Store short audio files in a `sounds/` directory. Use the existing `play_audio_file` method. Pause current music, play the effect, resume. Use autocomplete to list available sounds. Could add a `ui.Select` dropdown for browsing sounds.

**Complexity:** Medium -- Audio file management, pause/resume coordination, autocomplete for sound names.

---

### `/equalizer <preset>`
**Description:** Apply audio equalizer presets (bass boost, vocal boost, nightcore, vaporwave, etc.) using FFmpeg audio filters.

**User Value:** Customize the listening experience. "Bass boost" is a perennial favorite.

**discord.py Feasibility:** FFmpeg supports audio filters via `-af` option (e.g., `equalizer=f=100:width_type=h:width=200:g=10` for bass boost, `atempo=1.25,asetrate=48000*1.25` for nightcore). Modify `FFMPEG_OPTIONS` per guild. Use `app_commands.choices()` for preset selection.

**Complexity:** Medium -- FFmpeg filter string construction, per-guild preset storage, requires restarting audio source to apply.

---

### `/speed <multiplier>`
**Description:** Change playback speed (0.5x to 2.0x). Nightcore = 1.25x, slowed = 0.8x.

**User Value:** Nightcore and slowed+reverb are hugely popular on YouTube. Let users apply these effects live.

**discord.py Feasibility:** FFmpeg filter: `atempo=<speed>`. Needs audio source restart. Similar to equalizer implementation.

**Complexity:** Medium -- Same approach as equalizer, but simpler (single filter).

---

## 7. Enhanced Information & Discovery

### `/history [page]`
**Description:** Show recently played songs in the current server. Paginated list with timestamps.

**User Value:** "What was that song that played earlier?" -- very common question. Also useful for rediscovering songs.

**discord.py Feasibility:** The audit logger already tracks play events in SQLite. Query the audit database, format as paginated embed with `ui.View` buttons.

**Complexity:** Low -- Data already exists in audit database, just needs a query and display.

---

### `/songinfo [query]`
**Description:** Show detailed information about a song (duration, upload date, view count, channel, description snippet) without playing it.

**User Value:** Preview a song before adding it to the queue. Check details without committing.

**discord.py Feasibility:** Use yt-dlp to extract metadata without downloading. Format as a rich embed with thumbnail. Add an "Add to Queue" button.

**Complexity:** Low-Medium -- yt-dlp metadata extraction, embed formatting, optional button.

---

### `/similar`
**Description:** Show songs similar to the currently playing song, with buttons to queue them.

**User Value:** Music discovery without leaving the current session. "I like this, show me more like it."

**discord.py Feasibility:** Use the existing ytmusicapi `get_recommendations()` method. Display results in an embed with numbered `ui.Button` components to queue individual recommendations.

**Complexity:** Medium -- Recommendation fetch (already available), button-per-result View.

---

### `/trending [region]`
**Description:** Show trending music from YouTube Music for a specific region. Buttons to queue songs.

**User Value:** Discover what's popular right now. Good conversation starter.

**discord.py Feasibility:** ytmusicapi has `get_charts()` for trending data. Display as embed with queue buttons.

**Complexity:** Medium -- API integration, button view for queuing.

---

## 8. Server Management & Configuration

### `/settings`
**Description:** A central settings dashboard using a `ui.Select` dropdown to choose a setting category, then `ui.Modal` for editing values. Settings: default volume, autoplay on/off by default, DJ role, auto-disconnect timeout, announcement channel for now-playing, etc.

**User Value:** Centralized server configuration instead of scattered commands. Admin-friendly management interface.

**discord.py Feasibility:** Perfect use case for `ui.View` with `ui.Select` (category picker) + `ui.Modal` (value editor). discord.py Modals support `TextInput` fields for entering values. Use `interaction_check` to restrict to admins.

**Complexity:** High -- Multiple setting categories, Modal forms, database storage, applying settings across the bot.

---

### `/prefix` (or announcement config)
**Description:** Configure a text channel where the bot posts "Now Playing" announcements automatically when songs change.

**User Value:** Keeps a text channel updated with what's playing without anyone running `/nowplaying`. Good for large servers.

**discord.py Feasibility:** Store announcement channel ID in settings. In `play_next`, send an embed to the configured channel. Use `ui.ChannelSelect` for choosing the channel.

**Complexity:** Low-Medium -- Channel selection, settings storage, hook into play_next.

---

## 9. Interactive UI Enhancements (Not Commands)

### Now Playing Buttons
**Description:** Attach interactive buttons (Skip, Pause/Resume, Like/Dislike, Loop) to the now-playing embed that updates in real-time.

**User Value:** Eliminates the need to type commands for common actions. Click-to-control is faster and more intuitive, especially on mobile.

**discord.py Feasibility:** Create a persistent `ui.View` with buttons. Attach to the now-playing message. Use `custom_id` for persistence across bot restarts. The `interaction_check` can verify the user is in the same voice channel.

**Complexity:** Medium-High -- Persistent view, updating embed on state change, handling view timeouts and re-creation.

---

### Queue Pagination with Buttons
**Description:** Upgrade the `/queue` command to use Previous/Next buttons for paginated browsing. Each page shows 10 songs with position numbers.

**User Value:** Better UX for large queues. Current implementation truncates at 10 songs with "...and X more."

**discord.py Feasibility:** Standard `ui.View` with Previous/Next `ui.Button` components. Track current page in the View state.

**Complexity:** Low-Medium -- Standard pagination pattern with buttons.

---

### Song Request Modal
**Description:** A button on the now-playing embed that opens a `ui.Modal` with a text input for requesting songs. Combines search and queue in one interaction.

**User Value:** Streamlined song request flow. Opens a clean input form instead of requiring a separate `/play` command.

**discord.py Feasibility:** `ui.Modal` with a `ui.TextInput` for the search query. On submit, run the same search and queue logic as `/play`. Modal submissions get their own interaction to respond to.

**Complexity:** Medium -- Modal creation, search integration, response handling.

---

## Implementation Priority Matrix

| Priority | Command | Complexity | User Impact |
|----------|---------|-----------|-------------|
| **P0 - Quick Wins** | `/volume` | Very Low | High |
| | `/loop` | Low | High |
| | `/remove` | Low | Medium |
| | `/replay` | Low | Medium |
| | `/history` | Low | Medium |
| **P1 - High Value** | `/seek` | Medium | High |
| | `/lyrics` | Medium | High |
| | `/move`, `/skipto` | Low | Medium |
| | Queue pagination buttons | Low-Medium | Medium |
| | Now Playing buttons | Medium-High | High |
| **P2 - Features** | `/playlist save/load/list/delete` | Medium | High |
| | `/favorites add/list/play` | Low-Medium | Medium |
| | `/poll`, `/songpoll` | Medium | Medium |
| | `/similar` | Medium | Medium |
| | `/radio` | Medium | Medium |
| | `/share` | Medium | Medium |
| **P3 - Fun** | `/8ball`, `/coinflip` | Very Low | Low |
| | `/trivia` | High | High |
| | `/soundboard` | Medium | Medium |
| | `/equalizer`, `/speed` | Medium | Medium |
| **P4 - Advanced** | `/dj` | Medium | Medium |
| | `/settings` dashboard | High | Medium |
| | `/pomodoro`, `/timer` | Medium-High | Low-Medium |
| | `/schedule` | High | Low |
| | `/collab` mode | High | Medium |

---

## discord.py UI Components Summary

| Component | Class | Use Cases in This Bot |
|-----------|-------|----------------------|
| **Button** | `discord.ui.Button` | Skip/Pause/Like on now-playing, poll voting, pagination, "Add to Queue" on share/similar |
| **Select Menu** | `discord.ui.Select` | Genre/mood selection for radio, settings categories, soundboard browsing |
| **Channel Select** | `discord.ui.ChannelSelect` | Announcement channel configuration |
| **Modal** | `discord.ui.Modal` | Song request form, settings editor, playlist naming |
| **Text Input** | `discord.ui.TextInput` | Search query in modal, playlist name, timer message |
| **View** | `discord.ui.View` | Container for all interactive components; supports timeout and persistence |
| **Persistent View** | `View(timeout=None)` + `custom_id` | Now-playing controls that survive bot restarts |
| **Dynamic Item** | `discord.ui.DynamicItem` | Generic persistent buttons (e.g., queue-add buttons on old messages) |

**Key Constraints:**
- Max 5 `ActionRow` per message (each row holds up to 5 buttons or 1 select)
- Max 25 `ui.Select` options
- Modal supports up to 5 `TextInput` fields
- Embed description limit: 4096 characters
- Embed field value limit: 1024 characters
- Autocomplete: max 25 choices, each name max 100 chars

---

## Notes on Technical Approach

1. **Volume command** is the easiest win -- `MusicPlayerManager` already has `set_volume()` and `get_volume()`. Just add the slash command.

2. **Loop mode** should be an enum (`OFF`, `SINGLE`, `QUEUE`) stored on `GuildPlayer`. Modify `play_next()` to check loop state before popping the queue.

3. **Lyrics** could use the free [lrclib.net](https://lrclib.net) API (no API key required) which returns both synced and plain lyrics by song title and artist.

4. **Playlist system** should share the existing SQLite infrastructure from `settings.py` and `ratings.py`.

5. **Now Playing buttons** should be registered as persistent views in `setup_hook()` so they survive bot restarts. Use `custom_id` encoding like `np:skip:{guild_id}` for routing.

6. **Trivia game** can reuse the existing autoplay recommendation engine to select songs, combined with FFmpeg `-t 30` to play only a snippet.

7. **Seek** requires rebuilding the FFmpeg source with `-ss <seconds>` and careful tracking of elapsed time in `GuildPlayer`.
