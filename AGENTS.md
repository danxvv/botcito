# AGENTS.md

Guidance for coding agents working in this `discordbotcito` repository.

## Project Snapshot

- Discord bot focused on music playback, autoplay recommendations, recording, and AI assistant features.
- Python 3.10+ codebase with heavy async usage (`discord.py`, `yt-dlp`, SQLite, Agno).
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

# Quick syntax check (useful before commit)
uv run python -m compileall .
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

# Run one specific test function (most important)
uv run pytest tests/test_file.py::test_function -v

# Optional: run tests matching a keyword
uv run pytest tests/ -k "keyword" -v
```

## Environment and External Tools

Required runtime dependencies:
- `FFmpeg` for audio playback/transcoding.
- `Deno` or `Node.js` for yt-dlp JavaScript extraction.

Environment variables (`.env`):

```env
DISCORD_TOKEN=your_bot_token_here

# Optional /guide feature:
EXA_API_KEY=your_exa_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

## Repository Layout (Key Areas)

- `main.py`: Discord client setup and slash command handlers.
- `music_player.py`: per-guild player state, queue logic, autoplay, voice connection handling.
- `youtube.py`: async wrappers around blocking `yt-dlp` extraction.
- `autoplay.py`: YouTube Music recommendation logic.
- `voice_agent/`: voice conversation orchestration and TTS abstraction.
- `game_agent/`: AI assistant, session context, MCP connection management.
- `audit/`: audit database + textual TUI viewer.
- `settings.py`: SQLite-backed model/settings storage.

## Code Style and Conventions

### Imports

- Keep import groups in this order: standard library, third-party, local modules.
- Use a blank line between import groups (matches current files).
- Prefer relative imports inside packages (for example inside `game_agent/`, `audit/`, `voice_agent/`).

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
- Current code sometimes uses `typing.AsyncGenerator`; this is acceptable in existing files.

### Naming

- `snake_case`: functions, variables, modules.
- `PascalCase`: classes.
- `SCREAMING_SNAKE_CASE`: constants.
- Prefix internal helpers/fields with `_` when non-public.

### Data Modeling

- Prefer `@dataclass` for state/data containers (`SongInfo`, `GuildPlayer`, `ApiKeys`).
- Use `field(default_factory=...)` for mutable defaults.
- Use `frozen=True` only when immutable semantics are intended.

### Async and Concurrency Patterns

- Keep Discord and network/file operations async where possible.
- Offload blocking work (yt-dlp, heavy CPU) via `run_in_executor`.
- Protect shared mutable per-guild state with `asyncio.Lock`.
- From sync callbacks (e.g., voice `after`), schedule coroutines with `asyncio.run_coroutine_threadsafe`.

### Error Handling

- Raise specific exceptions for validation/config failures.
- Catch specific library exceptions where feasible (`DownloadError`, etc.).
- Keep user-facing error messages concise and safe (truncate where needed).
- Re-raise after logging when caller behavior depends on exception flow.

### Discord Bot Patterns

- Validate voice prerequisites early in slash commands.
- Defer interactions when work may take time (`await interaction.response.defer()`).
- Keep responses user-friendly; prefer ephemeral responses for user-specific failures.
- Respect guild-scoped state boundaries (`guild_id` keyed player/session state).

## Data and Persistence Notes

- SQLite files are created under `data/` at runtime.
- Important DB files:
  - `data/settings.db`
  - `data/audit.db`
  - `data/agent_memory.db`

## Agent Workflow Recommendations

- Make focused, minimal edits and preserve existing behavior unless task requires changes.
- Run targeted validation for touched areas (at least `compileall`; tests if present/added).
- Do not commit generated artifacts, secrets, or local runtime data.
- Prefer documenting new operational commands in `README.md` and this file.

## Cursor/Copilot Rules

- No Cursor rules were found (`.cursor/rules/` or `.cursorrules` absent).
- No Copilot instructions were found (`.github/copilot-instructions.md` absent).
- If these files are later added, treat them as higher-priority supplemental instructions and mirror key constraints in this document.
