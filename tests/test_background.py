"""Check that fire-and-forget tasks stay alive and report their failures."""

import asyncio
import gc
import logging

import background


def test_task_is_referenced_while_running_and_released_after():
    async def scenario():
        gate = asyncio.Event()
        done = []

        async def work():
            await gate.wait()
            done.append(True)

        task = background.spawn(work(), name="unit-work")
        del task
        gc.collect()  # Nothing but the helper keeps the task alive now.
        await asyncio.sleep(0)
        assert len(background._background_tasks) == 1
        gate.set()
        await asyncio.sleep(0.01)
        assert done == [True]
        assert not background._background_tasks

    asyncio.run(scenario())


def test_failures_are_logged_instead_of_lost(caplog):
    async def scenario():
        async def broken():
            raise RuntimeError("disk full")

        background.spawn(broken(), name="broken-job")
        await asyncio.sleep(0.01)

    with caplog.at_level(logging.ERROR, logger="background"):
        asyncio.run(scenario())
    assert any(
        "broken-job" in record.getMessage() and record.exc_info[1].args == ("disk full",)
        for record in caplog.records
    )
    assert not background._background_tasks


def test_cancelled_tasks_are_not_reported_as_failures(caplog):
    async def scenario():
        task = background.spawn(asyncio.sleep(10), name="sleeper")
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0.01)

    with caplog.at_level(logging.ERROR, logger="background"):
        asyncio.run(scenario())
    assert not caplog.records
    assert not background._background_tasks
