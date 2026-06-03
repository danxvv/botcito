# AGENTS.md

Guidance for coding agents working in this `discordbotcito` repository.

## Project Snapshot

- Discord bot focused on YouTube music playback, autoplay recommendations, and music listening stats.
- Python 3.10+ codebase with async Discord voice playback (`discord.py`, `yt-dlp`, SQLite).
- Package/dependency workflow uses `uv` (prefer `uv` for all Python commands).

## Build, Run, and Verification Commands

Use these commands from repo root.

```bash
# Install/update dependencies
uv sync

# Run the bot
uv run python main.py

# Run audit TUI app
uv run audit

# Quick syntax check
uv run python -m compileall main.py commands audit audio_cache.py autoplay.py music_player.py ratings.py youtube.py
```

## Lint and Format

- No dedicated linter/formatter config is currently checked in (`ruff`, `black`, `mypy`, etc. not configured).
- Follow existing file style and keep edits minimal/diff-friendly.
- If adding lint tooling, add config to `pyproject.toml` and document commands here.

## Testing

- There is currently no `tests/` directory in the repository.
- When creating tests, use `pytest` under `tests/`.

```bash
# Run full test suite
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_file.py -v

# Run one specific test function
uv run pytest tests/test_file.py::test_function -v

# Optional: run tests matching a keyword
uv run pytest tests/ -k "keyword" -v
```

## Environment and External Tools

Required runtime dependencies:

- `FFmpeg` for audio playback/transcoding.
- `Deno`, `Node.js`, or `Bun` for yt-dlp JavaScript extraction.

Environment variables (`.env`):

```env
DISCORD_TOKEN=your_bot_token_here
```

## Repository Layout

- `main.py`: Discord client setup and slash command registration.
- `commands/music.py`: playback, queue, autoplay, and now-playing commands.
- `commands/stats.py`: music stats, leaderboard, and song rating commands.
- `music_player.py`: per-guild player state, queue logic, autoplay, voice connection handling.
- `youtube.py`: async wrappers around blocking `yt-dlp` extraction.
- `autoplay.py`: YouTube Music autocomplete and recommendation logic.
- `ratings.py`: SQLite-backed song rating storage.
- `audit/`: audit database + textual TUI viewer.

## Code Style and Conventions

### Imports

- Keep import groups in this order: standard library, third-party, local modules.
- Use a blank line between import groups.
- Prefer relative imports inside packages, for example inside `audit/`.

### Formatting

- Use 4-space indentation and keep formatting consistent with surrounding code.
- Prefer readable multi-line function signatures/calls when lines get long.
- Keep module docstring as a short first line in each module.
- Avoid broad stylistic rewrites in unrelated code.

### Types

- Add type hints for new/updated functions, including return types.
- Prefer Python 3.10+ type syntax:
  - `str | None` over `Optional[str]`
  - `dict[str, Any]` over `Dict[str, Any]`

### Naming

- `snake_case`: functions, variables, modules.
- `PascalCase`: classes.
- `SCREAMING_SNAKE_CASE`: constants.
- Prefix internal helpers/fields with `_` when non-public.

### Data Modeling

- Prefer `@dataclass` for state/data containers (`SongInfo`, `GuildPlayer`).
- Use `field(default_factory=...)` for mutable defaults.
- Use `frozen=True` only when immutable semantics are intended.

### Async and Concurrency Patterns

- Keep Discord and network/file operations async where possible.
- Offload blocking work such as yt-dlp extraction via `run_in_executor`.
- Protect shared mutable per-guild state with `asyncio.Lock`.
- From sync callbacks such as voice `after`, schedule coroutines with `asyncio.run_coroutine_threadsafe`.

### Error Handling

- Raise specific exceptions for validation/config failures.
- Catch specific library exceptions where feasible (`DownloadError`, etc.).
- Keep user-facing error messages concise and safe.
- Re-raise after logging when caller behavior depends on exception flow.

### Discord Bot Patterns

- Validate voice prerequisites early in slash commands.
- Defer interactions when work may take time (`await interaction.response.defer()`).
- Keep responses user-friendly; prefer ephemeral responses for user-specific failures.
- Respect guild-scoped state boundaries (`guild_id` keyed player state).

## Data and Persistence Notes

- SQLite files are created under `data/` at runtime.
- Important DB files:
  - `data/audit.db`
  - `data/ratings.db`

## Agent Workflow Recommendations

- Make focused, minimal edits and preserve existing behavior unless task requires changes.
- Run targeted validation for touched areas, at least `compileall`; tests if present/added.
- Do not commit generated artifacts, secrets, or local runtime data.
- Prefer documenting new operational commands in `README.md` and this file.
