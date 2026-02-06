# Music Providers & Audio Source Ideas

Research into new music providers, audio sources, and audio processing features that could enhance the Discord bot. Each idea includes a feasibility assessment, suggested libraries, and complexity estimate.

---

## Table of Contents

1. [Spotify Integration (Metadata + Playback Bridge)](#1-spotify-integration)
2. [SoundCloud Support](#2-soundcloud-support)
3. [Bandcamp Support](#3-bandcamp-support)
4. [Deezer Integration](#4-deezer-integration)
5. [Tidal Integration](#5-tidal-integration)
6. [Internet Radio / Live Streams](#6-internet-radio--live-streams)
7. [Podcast Support](#7-podcast-support)
8. [Audio Effects & Equalizer](#8-audio-effects--equalizer)
9. [Crossfade Between Tracks](#9-crossfade-between-tracks)
10. [Nightcore / Speed Effects](#10-nightcore--speed-effects)
11. [Bilibili & NicoNico Support](#11-bilibili--niconico-support)
12. [Twitch Live Audio Streams](#12-twitch-live-audio-streams)
13. [Local File Playback](#13-local-file-playback)
14. [Audio Source Separation (Vocals/Instrumental)](#14-audio-source-separation)
15. [Multi-Platform Search Aggregation](#15-multi-platform-search-aggregation)

---

## 1. Spotify Integration

**Description:** Allow users to paste Spotify track/album/playlist URLs or search Spotify's catalog. Since Spotify does not allow direct audio streaming via their API, the approach is to extract metadata (track name, artist) from Spotify and then find and play the matching track via YouTube/yt-dlp.

**Why it enhances the bot:** Spotify is the world's most popular streaming platform. Many users share Spotify links in Discord, and currently the bot cannot handle them. This is one of the most frequently requested features in Discord music bots.

**Python packages:**
- **spotipy** -- Lightweight, well-maintained Spotify Web API wrapper. Production/stable. Supports search, track info, playlist items, album tracks, and audio features. Requires a free Spotify Developer API key (client ID + secret).
  - PyPI: `spotipy` | Docs: [spotipy.readthedocs.io](https://spotipy.readthedocs.io)
- **SpotAPI** -- Alternative that emulates browser requests, no API key needed. Higher risk of breakage.
  - PyPI: `spotapi` | GitHub: [aran404/spotapi](https://github.com/aran404/spotapi)

**How it would work:**
1. User pastes a Spotify URL (track, album, or playlist)
2. Bot uses spotipy to extract track name + artist(s)
3. Bot searches YouTube via the existing `search_youtube()` function with `"{artist} - {track}"` query
4. Plays the YouTube result through the normal pipeline

**Feasibility:** High -- spotipy is mature and well-documented. The metadata-to-YouTube bridge pattern is proven by many Discord bots. No audio streaming license needed since playback goes through YouTube.

**Complexity:** Medium -- Need URL parsing for Spotify links (track/album/playlist formats), spotipy API setup, and a mapping layer to YouTube search. Playlists require pagination handling.

---

## 2. SoundCloud Support

**Description:** Add direct SoundCloud track and playlist playback. SoundCloud has a large library of independent artists, remixes, DJ sets, and content not available on YouTube.

**Why it enhances the bot:** SoundCloud hosts millions of tracks from independent artists, producers, and DJs that often cannot be found on YouTube. DJ mixes and long-form sets are especially popular on SoundCloud.

**Python packages:**
- **yt-dlp (built-in)** -- yt-dlp already includes a SoundCloud extractor. No additional library needed. Supports tracks, playlists, sets, and user uploads.
- **soundcloud.py** -- Python wrapper for v2 SoundCloud API. Does not require an API key.
  - GitHub: [7x11x13/soundcloud.py](https://github.com/7x11x13/soundcloud.py)
- **sclib (soundcloud-lib)** -- SoundCloud API wrapper with asyncio support, no credentials needed. Good for metadata/search.
  - PyPI: `soundcloud-lib` | GitHub: [3jackdaws/soundcloud-lib](https://github.com/3jackdaws/soundcloud-lib)

**How it would work:**
- Since yt-dlp already supports SoundCloud, the simplest approach is to detect SoundCloud URLs and pass them directly to the existing `extract_song_info()` function.
- For search functionality, use `soundcloud.py` or `sclib` to search SoundCloud's catalog and provide autocomplete suggestions similar to the existing YouTube Music autocomplete.

**Feasibility:** Very High -- yt-dlp handles the heavy lifting already. The bot's `youtube.py` module just needs SoundCloud URL detection, and yt-dlp handles audio extraction natively. Search requires a small wrapper around one of the SoundCloud libraries.

**Complexity:** Low -- yt-dlp already does the hard work. URL detection and search autocomplete are the main additions.

---

## 3. Bandcamp Support

**Description:** Support Bandcamp track and album URLs for playback. Bandcamp is the go-to platform for independent and niche music, with high-quality audio.

**Why it enhances the bot:** Bandcamp is the primary platform for indie, underground, and experimental music. Many artists release exclusively on Bandcamp before anywhere else. It offers higher audio quality than most streaming platforms.

**Python packages:**
- **yt-dlp (built-in)** -- yt-dlp includes a Bandcamp extractor (`BandcampIE`, `BandcampAlbumIE`, `BandcampWeeklyIE`). Supports individual tracks and full albums.

**How it would work:**
- Detect Bandcamp URLs (format: `*.bandcamp.com/track/*` or `*.bandcamp.com/album/*`) and pass them to yt-dlp.
- Album URLs would need handling to queue all tracks from the album.

**Feasibility:** Very High -- Fully supported by yt-dlp out of the box.

**Complexity:** Low -- Same pipeline as YouTube. Just need URL detection and album-to-queue logic.

---

## 4. Deezer Integration

**Description:** Support Deezer track/album/playlist URLs via metadata extraction, similar to the Spotify approach. Deezer has 90+ million tracks and is particularly popular in Europe, Africa, and Latin America.

**Why it enhances the bot:** Expands the bot's reach to users who primarily use Deezer. Deezer links are commonly shared in European and Latin American Discord communities.

**Python packages:**
- **deezer-python** -- Well-maintained, production-stable wrapper for the Deezer API. Python 3.10+. Latest release: v7.2.0 (September 2025). Actively maintained.
  - PyPI: `deezer-python` | Docs: [deezer-python.readthedocs.io](https://deezer-python.readthedocs.io)
  - GitHub: [browniebroke/deezer-python](https://github.com/browniebroke/deezer-python)
- **deezer-python-async** -- Async fork of deezer-python, built for async applications.
  - GitHub: [music-assistant/deezer-python-async](https://github.com/music-assistant/deezer-python-async)

**How it would work:**
1. Detect Deezer URLs (track/album/playlist)
2. Extract metadata (track name, artist) via deezer-python
3. Search YouTube for the matching track and play through existing pipeline

**Feasibility:** High -- The library is stable and well-documented. The metadata-bridge approach is straightforward. No API key needed for public data on Deezer.

**Complexity:** Medium -- Similar to Spotify integration. URL parsing + metadata extraction + YouTube bridge.

---

## 5. Tidal Integration

**Description:** Support Tidal track/album/playlist URLs via metadata extraction. Tidal is known for its high-fidelity audio and curated playlists.

**Why it enhances the bot:** Tidal has a loyal user base, especially among audiophiles. Supporting Tidal links makes the bot more versatile.

**Python packages:**
- **tidalapi** -- Unofficial Python API for Tidal. Supports tracks, albums, playlists, artist info. Requires Python 3.9+.
  - PyPI: `tidalapi` | GitHub: [tehkillerbee/python-tidal](https://github.com/tehkillerbee/python-tidal)
  - Docs: [tidalapi.netlify.app](https://tidalapi.netlify.app/)

**How it would work:**
1. Detect Tidal URLs
2. Extract track/artist metadata via tidalapi
3. Bridge to YouTube search for playback

**Caveats:** tidalapi requires user authentication (OAuth). This is more complex than Spotify/Deezer since there is no "public data" mode. The bot would need to authenticate once with a Tidal account.

**Feasibility:** Medium -- The library works but authentication adds friction. The metadata-bridge approach is the same, but setup is heavier.

**Complexity:** Medium-High -- OAuth flow for Tidal, plus the standard URL parsing and YouTube bridge.

---

## 6. Internet Radio / Live Streams

**Description:** Support internet radio stations via direct stream URLs (Shoutcast/Icecast HTTP streams). Users could play curated radio stations, genre-based stations, or custom stream URLs.

**Why it enhances the bot:** Internet radio provides continuous, hands-free music without needing to queue individual songs. Great for background music, genre exploration, and community listening sessions. Stations can include lo-fi, jazz, ambient, electronic, and countless other genres.

**Python packages / tools:**
- **FFmpeg (built-in)** -- FFmpeg can already consume HTTP/HTTPS audio streams natively. No additional library needed for playback.
- **pyradios** -- Python wrapper for the Radio Browser API, a community-driven directory of ~30,000+ internet radio stations searchable by name, genre, country, language, and bitrate.
  - PyPI: `pyradios` | GitHub: [andreztz/pyradios](https://github.com/andreztz/pyradios)

**How it would work:**
1. Add a `/radio` command with optional search/genre/country parameters
2. Use pyradios to search the Radio Browser API for stations
3. Pass the stream URL directly to FFmpegOpusAudio (FFmpeg handles HTTP streams natively)
4. Display "Now Playing" with station name and genre info
5. Stream continues until user stops it or switches to another song

**Feasibility:** Very High -- FFmpeg already handles stream URLs. pyradios provides a massive searchable station directory with no API key required.

**Complexity:** Low-Medium -- Stream playback is simple (FFmpeg does it). The main work is the `/radio` command UX, station search, and handling the continuous (non-ending) nature of radio streams vs. individual tracks.

---

## 7. Podcast Support

**Description:** Play podcasts by searching for shows and episodes, or by pasting RSS feed URLs. The bot would extract episode audio and stream it.

**Why it enhances the bot:** Podcasts are a growing content category. Being able to listen to podcasts together in a voice channel is a social experience that no other bot commonly offers.

**Python packages / tools:**
- **yt-dlp (built-in)** -- Supports many podcast platforms including Spreaker, Apple Podcasts pages, and others.
- **feedparser** -- Mature Python library for parsing RSS/Atom feeds (podcast RSS feeds contain direct MP3/audio URLs).
  - PyPI: `feedparser` (well-maintained, widely used)
- **FFmpeg (built-in)** -- Handles direct MP3/audio URLs from podcast RSS feeds.

**How it would work:**
1. User provides a podcast RSS feed URL or a known platform link
2. Parse the RSS feed with feedparser to get episode list and audio URLs
3. Play the audio URL directly through FFmpeg
4. Display episode title, show name, and duration

**Feasibility:** High -- RSS feeds are standardized and contain direct audio URLs. feedparser is extremely mature.

**Complexity:** Medium -- RSS parsing is simple, but building a good UX for browsing shows/episodes with Discord's interaction limits (dropdowns, pagination) adds complexity.

---

## 8. Audio Effects & Equalizer

**Description:** Real-time audio effects like bass boost, treble boost, 8D audio (panning), reverb, and a parametric equalizer. Applied as FFmpeg filters on the audio stream.

**Why it enhances the bot:** Audio effects are a hugely popular feature in Discord music bots. Bass boost alone is one of the most requested effects. This adds a fun, interactive dimension to listening.

**Approaches:**

### Approach A: FFmpeg Audio Filters (Recommended)
FFmpeg has extensive built-in audio filters that can be applied in real-time without additional libraries:
- **Bass boost:** `bass=g=10` or `equalizer=f=80:width_type=h:width=100:g=10`
- **Treble boost:** `treble=g=5`
- **Nightcore:** `atempo=1.06,asetrate=48000*1.25`
- **8D Audio:** `apulsator=hz=0.125`
- **Reverb:** `aecho=0.8:0.9:1000:0.3`
- **Volume normalization:** `loudnorm`

This is the simplest approach since the bot already uses FFmpegOpusAudio. Filters are passed via the `before_options` or `options` parameter.

### Approach B: Pedalboard (Spotify's Audio Library)
- **pedalboard** -- Spotify's open-source audio effects library. Studio-quality effects including reverb, compression, EQ (low shelf, high shelf, peak filters), chorus, delay, distortion, and more. Supports VST3 plugins.
  - PyPI: `pedalboard` | GitHub: [spotify/pedalboard](https://github.com/spotify/pedalboard)
  - Docs: [spotify.github.io/pedalboard](https://spotify.github.io/pedalboard/)
- Better quality than FFmpeg filters but requires processing audio data in Python (not real-time streaming). More suitable for pre-processing audio before playback.

### Approach C: Pydub
- **pydub** -- Simple high-level audio manipulation. Supports volume changes, fades, and basic effects. Not designed for real-time streaming; better for offline processing.
  - PyPI: `pydub` | GitHub: [jiaaro/pydub](https://github.com/jiaaro/pydub)

**Recommendation:** Use FFmpeg filters (Approach A) for real-time effects. It requires no additional dependencies and integrates perfectly with the existing FFmpegOpusAudio pipeline. An `/effects` or `/eq` command could let users toggle presets like bass boost, nightcore, 8D, etc.

**Feasibility:** Very High (FFmpeg approach) -- No new dependencies. Just FFmpeg filter strings.

**Complexity:** Low-Medium -- Adding FFmpeg filter options is straightforward. The main challenge is managing effect state per guild and re-applying filters when switching tracks.

---

## 9. Crossfade Between Tracks

**Description:** Smooth audio crossfade transitions between songs, similar to Spotify's crossfade feature. The end of one track fades out while the beginning of the next fades in, overlapping for a set duration.

**Why it enhances the bot:** Eliminates the jarring silence between tracks. Creates a DJ-like continuous listening experience, especially valued during parties or study sessions.

**Approaches:**
- **FFmpeg approach:** Use `afade=t=out` on the ending track and `afade=t=in` on the starting track, with overlapping playback managed by the bot.
- **pydub approach:** Pre-process crossfade in memory using pydub's `append(crossfade=ms)` method. Requires downloading/buffering tracks, which adds latency.

**Caveats:** Discord.py's voice client plays one audio source at a time. True crossfade (two sources overlapping) requires either:
1. Pre-mixing the crossfade segment into a single audio buffer
2. Using FFmpeg's `amix` filter to combine two input streams

This is architecturally non-trivial because the current design plays tracks sequentially.

**Feasibility:** Medium -- Technically possible but requires significant changes to the playback pipeline. Discord.py voice only supports one audio source at a time.

**Complexity:** High -- Requires buffering, pre-mixing, or dual-stream management. Significant refactor of `play_next()` logic.

---

## 10. Nightcore / Speed Effects

**Description:** Pitch-shift and speed-change effects to create nightcore (faster + higher pitch), slowed + reverb, or custom speed adjustments.

**Why it enhances the bot:** Nightcore and "slowed + reverb" are hugely popular on YouTube and TikTok. Users frequently request these effects in Discord music bots.

**Python packages / tools:**
- **FFmpeg (built-in)** -- Handles speed and pitch natively:
  - Nightcore: `atempo=1.06,asetrate=48000*1.25` (faster + higher pitch)
  - Slowed: `atempo=0.85,asetrate=48000*0.85` (slower + lower pitch)
  - Speed only (no pitch change): `atempo=1.5`
- **nightcore** -- Dedicated Python library for nightcore effects. Applies speed increase with automatic bass boost compensation.
  - PyPI: `nightcore`

**Recommendation:** Use FFmpeg filters. A `/speed` command with presets (nightcore, slowed, custom multiplier) is the simplest implementation.

**Feasibility:** Very High -- FFmpeg handles this natively.

**Complexity:** Low -- Just FFmpeg filter strings. Same pattern as audio effects above.

---

## 11. Bilibili & NicoNico Support

**Description:** Support playback from Bilibili (Chinese video platform) and NicoNico (Japanese video platform), both popular for music, covers, and vocaloid content.

**Why it enhances the bot:** These platforms host massive libraries of content not available on YouTube, especially vocaloid music, anime music covers, original compositions, and gaming content. Valuable for communities interested in Asian media.

**Python packages / tools:**
- **yt-dlp (built-in)** -- Has dedicated extractors for both platforms:
  - `BiliBiliIE`, `BiliBiliSearchIE`, `BiliBiliBangumiIE`, and more
  - `NiconicoIE`, `NiconicoPlaylistIE`, `NiconicoChannelPlusIE`

**How it would work:**
- Detect Bilibili/NicoNico URLs and pass them to yt-dlp (same as YouTube pipeline)
- NicoNico may require login cookies for some content

**Feasibility:** Very High -- yt-dlp handles both platforms natively.

**Complexity:** Low -- URL detection is the main task. Some NicoNico content requires authentication.

---

## 12. Twitch Live Audio Streams

**Description:** Pull audio from live Twitch streams and play them in voice channels. Useful for listening to music streams, DJ sets, or event broadcasts.

**Why it enhances the bot:** Twitch hosts many 24/7 music streams, DJ sets, and live concerts. Users could listen to these together in Discord voice channels.

**Python packages / tools:**
- **yt-dlp (built-in)** -- Has a Twitch extractor (`TwitchStreamIE`) that can extract live stream URLs.
- **streamlink** -- Dedicated library for extracting streaming URLs from Twitch and other live streaming platforms. More reliable than yt-dlp for live content.
  - PyPI: `streamlink` | Docs: [streamlink.github.io](https://streamlink.github.io/)

**How it would work:**
1. User provides a Twitch channel URL
2. Use yt-dlp or streamlink to get the live stream URL
3. Pass audio stream to FFmpeg for Opus conversion and playback

**Caveats:** Live streams are continuous (no end), so the bot needs to handle them differently from regular tracks (no "next song" trigger). Quality and latency vary.

**Feasibility:** High -- Both yt-dlp and streamlink support Twitch.

**Complexity:** Medium -- Live stream handling (continuous, no duration), stream recovery on drops, and UX for live vs. on-demand content.

---

## 13. Local File Playback

**Description:** Allow bot administrators to upload or specify local audio files for playback. Useful for sound effects, custom intros, jingles, or music not available online.

**Why it enhances the bot:** Enables playing custom audio content (server intros, sound effects, local music library). Useful for community events, game nights, or D&D sessions.

**How it would work:**
- Add a `/playlocal` command (admin-only) that accepts a file path or Discord attachment
- Downloaded attachments stored in a `data/audio/` directory
- FFmpegOpusAudio can play local files directly (already supported by discord.py)

**Feasibility:** Very High -- discord.py and FFmpeg already support local file playback natively.

**Complexity:** Low -- File handling and permission management are the main tasks. Security considerations around file paths are important.

---

## 14. Audio Source Separation

**Description:** Separate audio tracks into vocals, drums, bass, and other instruments using AI models. Useful for karaoke mode (remove vocals), instrumental playback, or isolated track listening.

**Why it enhances the bot:** A karaoke mode (vocals removed) would be a standout feature. Instrumental versions of songs are frequently requested.

**Python packages:**
- **Spleeter** -- Deezer's open-source AI source separation tool. Pre-trained models for 2-stem (vocals/accompaniment), 4-stem (vocals/drums/bass/other), and 5-stem separation.
  - PyPI: `spleeter` | GitHub: [deezer/spleeter](https://github.com/deezer/spleeter)
- **demucs** -- Meta's music source separation model. Higher quality than Spleeter but more resource-intensive.
  - PyPI: `demucs` | GitHub: [facebookresearch/demucs](https://github.com/facebookresearch/demucs)

**Caveats:** Both libraries require significant CPU/GPU resources and processing time. Not suitable for real-time processing. Would need to download the track first, process it, then play the result. Processing a 3-minute song takes 30-60+ seconds on CPU.

**Feasibility:** Medium -- The libraries work well but are resource-intensive. Not practical on low-end hosting. Would need a queueing/caching system for processed tracks.

**Complexity:** High -- Download + process + cache pipeline, resource management, processing time UX (progress updates), and large model downloads (~300MB for Spleeter, ~1GB for demucs).

---

## 15. Multi-Platform Search Aggregation

**Description:** A unified `/search` command that searches across multiple platforms simultaneously (YouTube, SoundCloud, Spotify, Bandcamp) and presents results in a single embed with platform icons.

**Why it enhances the bot:** Users don't have to know which platform hosts a specific track. The bot finds the best available source automatically.

**How it would work:**
1. User runs `/search <query>`
2. Bot searches YouTube (ytmusicapi), SoundCloud (sclib), and optionally Spotify (spotipy) in parallel
3. Results displayed in an embed with platform labels
4. User selects a result; bot plays it via the appropriate pipeline

**Feasibility:** High -- All the individual search APIs are available. asyncio makes parallel searching straightforward.

**Complexity:** Medium -- Parallel API calls, result deduplication, unified result formatting, and per-platform playback routing.

---

## Priority Recommendation

Based on impact vs. effort, here is a suggested implementation order:

| Priority | Feature | Complexity | Impact |
|----------|---------|-----------|--------|
| 1 | SoundCloud Support | Low | High |
| 2 | Bandcamp Support | Low | Medium |
| 3 | Audio Effects / EQ (FFmpeg) | Low-Medium | Very High |
| 4 | Nightcore / Speed Effects | Low | High |
| 5 | Spotify Link Support | Medium | Very High |
| 6 | Internet Radio | Low-Medium | Medium |
| 7 | Bilibili & NicoNico | Low | Medium |
| 8 | Deezer Link Support | Medium | Medium |
| 9 | Local File Playback | Low | Low-Medium |
| 10 | Podcast Support | Medium | Medium |
| 11 | Twitch Live Audio | Medium | Medium |
| 12 | Multi-Platform Search | Medium | High |
| 13 | Tidal Link Support | Medium-High | Low |
| 14 | Crossfade | High | Medium |
| 15 | Source Separation (Karaoke) | High | Medium |

**Quick wins (Low complexity, immediate value):** SoundCloud, Bandcamp, and Bilibili/NicoNico support -- all already work through yt-dlp and just need URL detection. Audio effects via FFmpeg filters require no new dependencies.

**High-impact medium effort:** Spotify link support is the single most impactful feature since Spotify links are ubiquitous in Discord. Internet radio via pyradios opens an entirely new content category.

**Long-term / ambitious:** Crossfade and source separation are architecturally complex but would make the bot truly distinctive.
