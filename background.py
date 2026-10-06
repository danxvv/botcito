"""Fire-and-forget tasks that stay referenced until they finish."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# The event loop only keeps weak references to tasks, so an unreferenced task
# can be garbage-collected while it is still running.
_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    """Run a coroutine in the background, keeping it alive and logging failures."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("Background task %s failed", task.get_name(), exc_info=error)
