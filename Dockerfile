# syntax=docker/dockerfile:1

FROM node:24-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:0.11.15 AS uv
FROM python:3.13.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .
# Keep the project editable: its data paths are relative to the source in /app.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev \
    && groupadd --gid 10001 botcito \
    && useradd --uid 10001 --gid botcito --create-home botcito \
    && mkdir -p /app/data \
    && chown botcito:botcito /app/data

USER botcito
# discord.py uses asyncio.run(), which handles SIGINT and closes the client.
STOPSIGNAL SIGINT
CMD ["python", "main.py"]
