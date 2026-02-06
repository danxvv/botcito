# Infrastructure & Developer Experience Improvements

Research document covering infrastructure, observability, deployment, scaling, and developer experience improvements for the Discord music bot.

---

## Table of Contents

1. [Docker Containerization](#1-docker-containerization)
2. [Web Dashboard & REST API](#2-web-dashboard--rest-api)
3. [Structured Logging](#3-structured-logging)
4. [Monitoring & Observability](#4-monitoring--observability)
5. [Database Consolidation & Migration to PostgreSQL](#5-database-consolidation--migration-to-postgresql)
6. [Redis Caching Layer](#6-redis-caching-layer)
7. [CI/CD Pipeline](#7-cicd-pipeline)
8. [Bot Sharding for Scale](#8-bot-sharding-for-scale)
9. [Cog/Extension Plugin System](#9-cogextension-plugin-system)
10. [Rate Limiting & Abuse Prevention](#10-rate-limiting--abuse-prevention)
11. [Configuration Hot-Reloading](#11-configuration-hot-reloading)
12. [Health Checks & Graceful Shutdown](#12-health-checks--graceful-shutdown)
13. [Backup & Migration Strategy](#13-backup--migration-strategy)
14. [Error Handling & Resilience Patterns](#14-error-handling--resilience-patterns)
15. [Webhook & Cross-Platform Integrations](#15-webhook--cross-platform-integrations)

---

## 1. Docker Containerization

### Description

Package the bot and all its dependencies (FFmpeg, Deno/Node.js, Python, uv, PyTorch) into a Docker image for reproducible deployments. The bot currently requires manual installation of FFmpeg and Deno/Node.js on the host -- Docker eliminates "works on my machine" issues entirely.

### Value Proposition

- **Reproducible builds**: Every deployment uses the exact same environment regardless of host OS.
- **Simplified onboarding**: New contributors run `docker compose up` instead of installing 5+ system dependencies.
- **Production parity**: Dev and prod run identical environments.
- **Easy rollbacks**: Tag images per release, rollback is just pointing to a previous tag.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **Docker** + **Docker Compose** | Container runtime and orchestration | Extremely mature, industry standard |
| **ghcr.io/astral-sh/uv:python3.12-bookworm-slim** | Official uv base image | Actively maintained by Astral |
| **Multi-stage builds** | Reduce final image size by excluding build tools | Docker best practice |

### Implementation Approach

Use a multi-stage Dockerfile following the official uv-docker-example patterns:

**Stage 1 (Builder)**: Install dependencies with uv into a venv using cache mounts.
```
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
```

**Stage 2 (Runtime)**: Copy only the venv and app code, install FFmpeg + Deno system packages.
```
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER nonroot
CMD ["python", "main.py"]
```

**Docker Compose** for local dev with volume mounts for hot-reload:
```yaml
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data  # Persist SQLite databases
      - ./cookies.txt:/app/cookies.txt:ro
```

### Complexity: Medium

The main challenge is getting PyTorch + CUDA working in Docker (requires nvidia-container-toolkit for GPU TTS). A CPU-only variant would be straightforward. Consider providing both `Dockerfile` (CPU) and `Dockerfile.gpu` (CUDA) variants.

---

## 2. Web Dashboard & REST API

### Description

Add a FastAPI-based web server running alongside the bot to provide a REST API for external control and a web dashboard for monitoring. This complements the existing Textual TUI audit viewer with a browser-accessible interface.

### Value Proposition

- **Remote monitoring**: Check bot status from anywhere via browser, not just the machine running the TUI.
- **External integrations**: Other tools/scripts can control the bot via REST endpoints (queue songs, check status, view stats).
- **Mobile access**: Server admins can monitor from phone browsers.
- **Foundation for future**: WebSocket support enables real-time "now playing" widgets for streams/overlays.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **FastAPI** (v0.115+) | Async web framework with auto-generated OpenAPI docs | Very mature, huge community (benchmark score 96.8) |
| **Uvicorn** | ASGI server | Production-proven |
| **Jinja2** | Server-side HTML templates for dashboard | Extremely mature |
| **WebSockets** (built into FastAPI) | Real-time "now playing" updates | Stable |

### Implementation Approach

Run FastAPI in the same process as the bot using a shared event loop. Use FastAPI's lifespan events for startup/shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bot is already running, just register shared state
    yield
    # Cleanup

app = FastAPI(lifespan=lifespan)
```

**Key endpoints:**
- `GET /api/status` -- Bot uptime, guild count, voice connections
- `GET /api/guilds/{id}/queue` -- Current queue for a guild
- `GET /api/guilds/{id}/nowplaying` -- Currently playing song
- `POST /api/guilds/{id}/skip` -- Skip current song (with auth)
- `GET /api/stats` -- Aggregate stats from audit database
- `GET /api/health` -- Health check endpoint
- `GET /dashboard` -- HTML dashboard rendering stats/status

**Security**: Use a simple API key from `.env` for the REST API. The dashboard can be password-protected or restricted to localhost.

### Complexity: Medium

FastAPI is straightforward to set up. The main challenge is safely sharing state between the Discord bot and the web server (the `MusicPlayerManager` and audit database). Using the same asyncio event loop and the existing `asyncio.Lock` patterns in the codebase handles this naturally.

---

## 3. Structured Logging

### Description

Replace the current `print()` debug statements scattered throughout the codebase (e.g., `print(f"[DEBUG] Downloading: {song.title}")`) with structured logging using `structlog`. This produces machine-parseable JSON logs in production while keeping human-readable colored output in development.

### Value Proposition

- **Searchability**: JSON logs can be queried by field (e.g., "show all errors for guild X" or "all yt-dlp failures").
- **Context propagation**: Automatically include guild_id, user_id, song_id in every log line without manual formatting.
- **Log levels**: Filter noise -- DEBUG for development, WARNING+ for production.
- **Integration**: JSON logs feed directly into log aggregators (Grafana Loki, ELK, CloudWatch).
- **No code churn**: structlog wraps stdlib logging, so existing `logging.getLogger()` calls (already used in `autoplay.py`, `audio_cache.py`) keep working.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **structlog** (v24+) | Structured logging with JSON/console output | Very mature, benchmark score 91.1 |
| **python-json-logger** (alternative) | JSON formatter for stdlib logging | Mature but less featured |

### Implementation Approach

1. Add `structlog` to dependencies.
2. Configure once at startup in `main.py`:
   ```python
   import structlog
   structlog.configure(
       processors=[
           structlog.contextvars.merge_contextvars,
           structlog.processors.add_log_level,
           structlog.processors.TimeStamper(fmt="iso"),
           structlog.dev.ConsoleRenderer()  # or JSONRenderer() in prod
       ]
   )
   ```
3. Replace `print(f"[DEBUG] ...")` calls with `log.debug("downloading", title=song.title)`.
4. Use `structlog.contextvars` to bind guild_id/user_id once per command, then every subsequent log line includes it automatically.

### Current state of logging in the codebase

The project uses a mix of approaches:
- **`print()` statements**: `music_player.py` (17 print calls), `audio_cache.py` (4 print calls), `youtube.py` (2 print calls), `main.py` (3 print calls)
- **`logging.getLogger()`**: `autoplay.py`, `audio_cache.py` -- already using proper logging
- **Audit logger**: `audit/logger.py` -- writes to SQLite, separate concern

Migrating is low-risk since structlog wraps stdlib logging seamlessly.

### Complexity: Low

---

## 4. Monitoring & Observability

### Description

Instrument the bot with Prometheus metrics to track operational health: songs played, queue lengths, voice connections, yt-dlp failures, FFmpeg errors, latency, and AI response times. Expose metrics via an HTTP endpoint for scraping.

### Value Proposition

- **Proactive alerting**: Get notified when yt-dlp error rates spike (YouTube API changes), not when users complain.
- **Capacity planning**: Track concurrent voice connections and queue sizes to understand growth patterns.
- **Debugging**: Histograms of yt-dlp extraction time and FFmpeg startup time reveal performance regressions.
- **AI cost tracking**: Count LLM API calls and track response latency per model.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **prometheus_client** | Official Python Prometheus client (benchmark score 95.1) | Very mature, actively maintained |
| **Grafana** | Visualization dashboards | Industry standard |
| **Prometheus** | Metrics scraping and storage | Industry standard |

### Implementation Approach

Define metrics relevant to the bot's domain:

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Playback metrics
songs_played = Counter('bot_songs_played_total', 'Songs played', ['guild_id', 'source'])
queue_length = Gauge('bot_queue_length', 'Current queue length', ['guild_id'])
voice_connections = Gauge('bot_voice_connections', 'Active voice connections')

# Error metrics
ytdlp_errors = Counter('bot_ytdlp_errors_total', 'yt-dlp extraction failures', ['error_type'])
ffmpeg_errors = Counter('bot_ffmpeg_errors_total', 'FFmpeg playback failures')

# Latency metrics
ytdlp_duration = Histogram('bot_ytdlp_duration_seconds', 'yt-dlp extraction time')
ai_response_duration = Histogram('bot_ai_response_seconds', 'AI response latency', ['model'])

# Start metrics server on a separate port
start_http_server(9090)
```

If using the FastAPI dashboard (see item #2), mount metrics directly:
```python
from prometheus_client import make_asgi_app
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

### Complexity: Low-Medium

Adding counters and gauges to existing code paths is straightforward. The main work is choosing the right metric points and setting up Grafana dashboards.

---

## 5. Database Consolidation & Migration to PostgreSQL

### Description

The bot currently uses **three separate SQLite databases** with raw `sqlite3` connections:
- `data/settings.db` -- Bot settings (LLM model preference)
- `data/audit.db` -- Command and music audit logs
- `data/ratings.db` -- Song ratings

Each module manages its own connection lifecycle differently. Consolidating to a single database engine (optionally PostgreSQL for production) with a unified connection layer would reduce complexity.

### Value Proposition

- **Unified schema management**: One migration system instead of three independent `init_db()` calls.
- **Cross-table queries**: Join ratings with audit logs to answer "which songs get skipped most?"
- **Concurrent access**: SQLite's single-writer limitation can cause `database is locked` errors under load. PostgreSQL handles concurrent writes natively.
- **Connection pooling**: Reuse connections instead of opening/closing per query.
- **Production readiness**: PostgreSQL is battle-tested for multi-guild bots with heavy write loads.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **SQLAlchemy 2.0** (async) | ORM + connection pooling + migrations | Very mature, already a dependency |
| **Alembic** | Database schema migrations | Standard for SQLAlchemy projects |
| **aiosqlite** | Async SQLite driver (for keeping SQLite in dev) | Mature |
| **asyncpg** | High-performance async PostgreSQL driver | Very mature |

### Implementation Approach

1. **Phase 1 -- Consolidate**: Merge all three schemas into one database file. Use SQLAlchemy ORM models instead of raw SQL strings. The project already has SQLAlchemy as a dependency but only the audit module uses it partially.

2. **Phase 2 -- Async**: Switch from synchronous `sqlite3.connect()` to async SQLAlchemy with `aiosqlite` backend. This eliminates the thread-safety concerns in `audit/logger.py` (which currently uses a threading.Lock for double-check initialization).

3. **Phase 3 -- PostgreSQL option**: Make the database URL configurable via `.env`:
   ```
   DATABASE_URL=sqlite:///data/bot.db        # Development
   DATABASE_URL=postgresql+asyncpg://...      # Production
   ```

4. **Phase 4 -- Migrations**: Use Alembic for schema versioning so database changes are trackable and reversible.

### Complexity: High

This touches many modules (`settings.py`, `ratings.py`, `audit/database.py`, `audit/logger.py`) and requires careful data migration. Best done incrementally.

---

## 6. Redis Caching Layer

### Description

Add Redis for caching frequently-accessed data: YouTube Music recommendations, yt-dlp extraction results, and LLM responses. The bot currently uses in-memory caches (`OrderedDict` in `autoplay.py`, `dict` in `audio_cache.py`) that are lost on restart.

### Value Proposition

- **Persistence across restarts**: Recommendation cache and extraction results survive bot restarts.
- **Shared state**: If sharding (see item #8), all shards can share the same cache.
- **TTL support**: Automatically expire stale YouTube stream URLs (they expire after ~6 hours) without manual eviction logic.
- **Rate limiting**: Redis is the standard backend for rate limiting (see item #10).

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **redis-py** (async) | Official Redis client with asyncio support | Very mature |
| **Redis Stack** | Redis with JSON, search, and time-series modules | Production-ready |
| **valkey** (alternative) | Open-source Redis fork | Growing, fully compatible |

### Implementation Approach

Replace the in-memory `OrderedDict` recommendation cache in `YouTubeMusicHandler` with Redis:

```python
import redis.asyncio as redis

class YouTubeMusicHandler:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get_recommendations(self, video_id: str, limit: int = 10):
        cached = await self.redis.get(f"recs:{video_id}")
        if cached:
            return json.loads(cached)[:limit]
        # ... fetch from API ...
        await self.redis.setex(f"recs:{video_id}", 3600, json.dumps(recs))
```

**Make it optional**: Fall back to in-memory caching when Redis is not configured. This keeps the development experience simple.

### Complexity: Medium

---

## 7. CI/CD Pipeline

### Description

Set up GitHub Actions for automated testing, linting, and deployment. The project currently has no CI pipeline -- there are no test files in the repository.

### Value Proposition

- **Catch regressions early**: Automated checks on every PR prevent broken code from merging.
- **Code quality**: Enforce consistent style with ruff (fast Python linter, already used in the uv ecosystem).
- **Automated deployment**: Push to main triggers automatic deployment (Docker build + push or SSH deploy).
- **Dependency security**: Automated scanning for known vulnerabilities in dependencies.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **GitHub Actions** | CI/CD platform | Industry standard, free for public repos |
| **ruff** | Extremely fast Python linter and formatter | Very mature, same ecosystem as uv |
| **pytest** | Testing framework | Industry standard |
| **pytest-asyncio** | Async test support | Mature |
| **Dependabot** / **Renovate** | Automated dependency updates | Built into GitHub |

### Implementation Approach

Create `.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run pytest tests/ -v

  docker:
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: github.ref == 'refs/heads/master'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
```

**Testing strategy**: Start with unit tests for pure functions (`ratings.py`, `settings.py`, `autoplay.py` recommendation filtering) and integration tests for the audio cache. Mock Discord and YouTube APIs.

### Complexity: Low-Medium

Setting up the CI pipeline itself is low complexity. Writing meaningful tests is medium complexity but high value.

---

## 8. Bot Sharding for Scale

### Description

Use discord.py's built-in `AutoShardedClient` to automatically split the bot across multiple shards when it reaches 1000+ guilds. Discord requires sharding at 2500 guilds, but it is recommended to start at 1000.

### Value Proposition

- **Required for growth**: Discord mandates sharding above 2500 guilds. Planning ahead avoids emergency rewrites.
- **Better performance**: Each shard handles fewer guilds, reducing event processing latency.
- **Transparent**: `AutoShardedClient` is a drop-in replacement for `Client` -- existing code works as-is.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **discord.AutoShardedClient** | Built-in automatic sharding | Part of discord.py, very mature |
| **discord.AutoShardedBot** | Same but for Bot subclass (command extension) | Part of discord.py |

### Implementation Approach

The change is minimal for single-process sharding:

```python
# In main.py, change the base class:
class MusicBot(discord.Client):  # Current
class MusicBot(discord.AutoShardedClient):  # Sharded
```

Or conditionally based on guild count:
```python
class MusicBot(discord.AutoShardedClient if ENABLE_SHARDING else discord.Client):
```

**Considerations for the music bot specifically:**
- `GuildPlayer` instances are already guild-scoped (keyed by `guild_id` in `MusicPlayerManager.players`), so they naturally partition across shards.
- Voice connections are per-shard, which is handled automatically.
- If moving to multi-process sharding later, the `MusicPlayerManager` state would need to be externalized (Redis/database), which ties into item #6.

### Complexity: Low (single-process) / High (multi-process)

Single-process auto-sharding is a one-line change. Multi-process sharding with IPC requires significant architecture changes.

---

## 9. Cog/Extension Plugin System

### Description

Refactor the bot's command modules into discord.py Cogs (extensions) for better modularity and hot-reloading. Currently, the bot uses a flat `commands/` package with `setup_*()` functions that register slash commands directly on the client's command tree. Cogs provide a structured pattern with lifecycle hooks, shared state, and the ability to load/unload modules at runtime.

### Value Proposition

- **Hot-reloading**: Load/unload/reload command modules without restarting the bot (great for development).
- **Encapsulation**: Each Cog owns its state, listeners, and commands in a self-contained class.
- **Third-party plugins**: Community contributors can write Cogs that plug into the bot without modifying core code.
- **Error isolation**: A failing Cog can be unloaded without taking down the entire bot.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **discord.ext.commands.Cog** | Built-in extension system | Part of discord.py, very mature |
| **discord.ext.commands.Bot** | Bot class with Cog support | Part of discord.py |

### Implementation Approach

The current structure in `commands/__init__.py` registers commands via `setup_*()` functions. Converting to Cogs:

**Before** (`commands/music.py`):
```python
def setup(client):
    @client.tree.command(name="play")
    async def play(interaction, query: str):
        ...
```

**After** (`cogs/music.py`):
```python
class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="play")
    async def play(self, interaction, query: str):
        ...

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
```

This also requires changing `MusicBot` to extend `commands.Bot` instead of `discord.Client`. The command tree syncing and registration is then handled automatically.

### Complexity: Medium

Each of the 5 command modules (`music`, `stats`, `recording`, `voice`, `guide`) needs to be wrapped in a Cog class. The logic stays the same; it is primarily a structural refactor.

---

## 10. Rate Limiting & Abuse Prevention

### Description

Add per-user and per-guild rate limiting to prevent abuse (e.g., spamming `/play` commands, flooding the AI `/guide` endpoint). Currently, there is no rate limiting beyond Discord's built-in interaction rate limits.

### Value Proposition

- **Cost protection**: The `/guide` command calls paid LLM APIs. Unlimited use could generate unexpected bills.
- **Fair usage**: Prevent one user from monopolizing the bot in a shared server.
- **Stability**: Rapid-fire `/play` commands can overwhelm yt-dlp's ThreadPoolExecutor (max 3 workers).

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **discord.app_commands.checks.cooldown** | Built-in per-user cooldowns | Part of discord.py |
| **Custom in-memory rate limiter** | Token bucket or sliding window | Simple to implement |
| **Redis-based rate limiter** | Distributed rate limiting (if sharded) | Standard pattern |

### Implementation Approach

**Quick win -- discord.py built-in cooldowns:**
```python
@app_commands.checks.cooldown(rate=1, per=5.0)  # 1 use per 5 seconds
@client.tree.command(name="play")
async def play(interaction, query: str):
    ...
```

**Custom rate limiter for the AI endpoint:**
```python
class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: dict[int, list[float]] = {}  # user_id -> timestamps

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        user_calls = self.calls.setdefault(user_id, [])
        user_calls[:] = [t for t in user_calls if now - t < self.period]
        if len(user_calls) >= self.max_calls:
            return False
        user_calls.append(now)
        return True

guide_limiter = RateLimiter(max_calls=5, period=60)  # 5 per minute
```

**Per-guild daily limits** for expensive operations (AI queries):
```python
# Using the existing audit database to count usage
from audit.database import get_guild_command_count
if get_guild_command_count(guild_id, hours=24) > 100:
    return "Daily limit reached"
```

### Complexity: Low

---

## 11. Configuration Hot-Reloading

### Description

Allow changing bot configuration (LLM model, autoplay defaults, rate limits, volume defaults) without restarting. The bot currently reads settings from `.env` at startup and from SQLite for the LLM model. Other settings are hardcoded constants.

### Value Proposition

- **Zero-downtime changes**: Adjust behavior without disconnecting active voice sessions.
- **Experimentation**: Quickly test different LLM models, FFmpeg options, or cache sizes.
- **Ops-friendly**: Server administrators can tune the bot via Discord commands or the web dashboard.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **watchfiles** (watchgod successor) | File system watcher for config changes | Mature, async-native |
| **pydantic-settings** | Typed configuration with validation and env var loading | Very mature |
| **Existing SQLite settings** | Already supports runtime changes via `/model` command | In-place |

### Implementation Approach

1. **Centralize configuration** into a single `BotConfig` pydantic model:
   ```python
   from pydantic_settings import BaseSettings

   class BotConfig(BaseSettings):
       discord_token: str
       llm_model: str = "google/gemini-3-flash-preview"
       disconnect_timeout: int = 300
       max_queue_size: int = 100
       autoplay_prefetch_count: int = 3
       tts_provider: str = "qwen"

       class Config:
           env_file = ".env"
   ```

2. **Replace scattered constants** (like `DISCONNECT_TIMEOUT = 300`, `AUTOPLAY_PREFETCH_COUNT = 3` in `music_player.py`) with references to the config object.

3. **Extend the existing `/model` command pattern** to support more settings: `/config set disconnect_timeout 600`.

### Complexity: Low-Medium

---

## 12. Health Checks & Graceful Shutdown

### Description

Add health check endpoints and graceful shutdown handling to ensure the bot can be monitored by orchestrators (Docker, systemd, Kubernetes) and cleanly terminate without corrupting state.

### Value Proposition

- **Container orchestration**: Docker/Kubernetes can automatically restart unhealthy instances.
- **Clean state**: Graceful shutdown saves in-progress recordings, flushes audit logs, and disconnects from voice channels cleanly.
- **Dependency health**: Check that FFmpeg, Deno, and external APIs are reachable.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **FastAPI health endpoint** (see item #2) | HTTP health check | Standard pattern |
| **signal handlers** (stdlib) | Catch SIGTERM/SIGINT for graceful shutdown | Built into Python |
| **Docker HEALTHCHECK** | Container-level health monitoring | Built into Docker |

### Implementation Approach

**Health check endpoint** (if using FastAPI):
```python
@app.get("/health")
async def health():
    checks = {
        "discord": client.is_ready(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "database": check_db_connection(),
        "voice_connections": len([p for p in player_manager.players.values() if p.voice_client]),
    }
    healthy = all([checks["discord"], checks["ffmpeg"], checks["database"]])
    return {"status": "healthy" if healthy else "degraded", "checks": checks}
```

**Graceful shutdown**:
```python
import signal

async def graceful_shutdown():
    # Disconnect all voice clients and save recordings
    for guild_id, player in player_manager.players.items():
        if player.recording_session:
            await player_manager.stop_recording(guild_id)
        if player.voice_client:
            await player_manager.disconnect(guild_id)
    # Flush audit logs
    # Close database connections
    await client.close()
```

**Docker HEALTHCHECK**:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
```

### Complexity: Low

---

## 13. Backup & Migration Strategy

### Description

Implement automated backup of SQLite databases and a migration strategy for schema changes. Currently the three SQLite databases (`settings.db`, `audit.db`, `ratings.db`) have no backup or versioning mechanism.

### Value Proposition

- **Data safety**: Automated backups prevent data loss from corruption, accidental deletion, or failed upgrades.
- **Schema evolution**: As the bot grows, database schemas need to change. Without migrations, schema changes require manual intervention or data loss.
- **Disaster recovery**: Quick restore from backup if something goes wrong.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **sqlite3 `.backup()` API** | Online backup of SQLite databases | Built into Python stdlib |
| **Alembic** | Schema migration management | Standard for SQLAlchemy |
| **Scheduled tasks (asyncio)** | Periodic backup execution | Built into Python |
| **Cloud storage** (S3, GCS) | Offsite backup storage | Optional |

### Implementation Approach

**Automated daily backups**:
```python
import sqlite3
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("data/backups")

def backup_database(db_path: Path, backup_dir: Path = BACKUP_DIR):
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{timestamp}.db"

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    source.close()
    dest.close()

    # Keep only last 7 backups
    backups = sorted(backup_dir.glob(f"{db_path.stem}_*.db"))
    for old in backups[:-7]:
        old.unlink()
```

**Run on a schedule** using `asyncio.create_task` with a sleep loop, or trigger it via the `/config` command.

**Schema migrations with Alembic** (ties into item #5):
```
alembic init migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### Complexity: Low (backups) / Medium (Alembic migrations)

---

## 14. Error Handling & Resilience Patterns

### Description

Improve error handling across the bot with retry logic, circuit breakers, and better error reporting to users. Currently, errors in yt-dlp, FFmpeg, and AI responses are caught and logged but often result in silent failures (the user sees no feedback).

### Value Proposition

- **User experience**: Users get clear error messages instead of silent failures.
- **Self-healing**: Transient failures (network timeouts, API rate limits) are automatically retried.
- **Stability**: Circuit breakers prevent cascading failures when external services are down.
- **Debuggability**: Centralized error handling makes it easier to track down issues.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **tenacity** | Retry library with decorators for Python | Very mature, widely used |
| **Custom circuit breaker** | Prevent hammering failed services | Simple to implement |
| **discord.py error handlers** | Global and per-command error handling | Built into discord.py |

### Implementation Approach

**Retry for yt-dlp extractions** (the most common failure point):
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type((DownloadError, ExtractorError)),
)
def _extract_info(url: str, *, playlist: bool = False):
    ...
```

**Global error handler for Discord commands**:
```python
@client.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Cooldown: try again in {error.retry_after:.0f}s", ephemeral=True
        )
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Permission denied.", ephemeral=True)
    else:
        logger.error("Unhandled command error", exc_info=error)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)
```

**Circuit breaker for external APIs**:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.last_failure = 0
        self.state = "closed"  # closed = working, open = failing

    def is_open(self):
        if self.state == "open":
            if time.time() - self.last_failure > self.reset_timeout:
                self.state = "half-open"
                return False
            return True
        return False
```

### Complexity: Low-Medium

---

## 15. Webhook & Cross-Platform Integrations

### Description

Add webhook support to send bot events (songs played, errors, AI responses) to external services like Slack, Telegram, or custom webhooks. This enables cross-platform notifications and integration with other tools.

### Value Proposition

- **Cross-team visibility**: Server admins who prefer Slack/Telegram get notified about bot activity.
- **Monitoring integration**: Send error alerts to PagerDuty, Opsgenie, or Slack channels.
- **Activity feeds**: Post "now playing" updates to a Telegram channel or Slack workspace.
- **Extensibility**: Generic webhook support lets users build custom integrations.

### Suggested Tools & Libraries

| Tool | Purpose | Maturity |
|------|---------|----------|
| **httpx** (async) | HTTP client for sending webhooks | Very mature, already in dependency tree |
| **Discord Webhooks** | Send messages to Discord channels programmatically | Built into Discord API |

### Implementation Approach

Create a generic webhook dispatcher that fires on configurable events:

```python
class WebhookDispatcher:
    def __init__(self):
        self.webhooks: list[dict] = []  # Loaded from settings

    async def dispatch(self, event: str, data: dict):
        async with httpx.AsyncClient() as client:
            for hook in self.webhooks:
                if event in hook["events"]:
                    await client.post(hook["url"], json={
                        "event": event,
                        "timestamp": datetime.utcnow().isoformat(),
                        **data
                    })
```

**Supported events**: `song_played`, `song_skipped`, `bot_error`, `voice_connected`, `voice_disconnected`, `ai_response`.

**Configuration via settings DB or `.env`**:
```
WEBHOOK_URLS=https://hooks.slack.com/services/xxx,https://api.telegram.org/botXXX/sendMessage
WEBHOOK_EVENTS=bot_error,voice_disconnected
```

### Complexity: Low-Medium

---

## Priority Recommendations

Based on the current state of the codebase, here is a suggested implementation order, balancing impact against effort:

### Quick Wins (Low effort, high impact)
1. **Structured Logging** (#3) -- Replace print statements, immediate debugging improvement
2. **Rate Limiting** (#10) -- Protect against AI API cost overruns
3. **Health Checks** (#12) -- Essential for any production deployment

### Medium-Term Improvements
4. **CI/CD Pipeline** (#7) -- Foundation for code quality and automated deployments
5. **Docker Containerization** (#1) -- Reproducible deployments, simpler onboarding
6. **Error Handling & Resilience** (#14) -- Better UX and stability
7. **Cog/Extension System** (#9) -- Better code organization, hot-reloading

### Strategic Investments
8. **Web Dashboard & REST API** (#2) -- Remote monitoring and external integrations
9. **Monitoring & Observability** (#4) -- Proactive issue detection
10. **Configuration Hot-Reloading** (#11) -- Operational flexibility

### Long-Term Architecture
11. **Database Consolidation** (#5) -- Foundation for advanced features
12. **Redis Caching** (#6) -- Performance and scaling foundation
13. **Bot Sharding** (#8) -- Only needed at 1000+ guilds
14. **Backup Strategy** (#13) -- Data safety
15. **Webhook Integrations** (#15) -- Cross-platform connectivity
