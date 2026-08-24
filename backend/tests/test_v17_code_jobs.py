from __future__ import annotations

import asyncio

from app.v17.jobs import (
    cancel_build_job,
    create_build_job,
    get_build_job,
)


def test_async_job_completes_and_returns_result():
    async def scenario():
        async def runner(progress):
            await progress("planning", 10, "Planning")
            await asyncio.sleep(0)
            await progress("packaging", 90, "Packaging")
            return {"project_name": "demo", "answer": "ready"}

        created = await create_build_job(
            user_id="u1",
            runner=runner,
        )
        job_id = created["job_id"]

        for _ in range(50):
            state = await get_build_job(
                user_id="u1",
                job_id=job_id,
            )
            if state and state["status"] == "succeeded":
                break
            await asyncio.sleep(0.01)

        assert state is not None
        assert state["status"] == "succeeded"
        assert state["progress"] == 100
        assert state["result"]["project_name"] == "demo"

    asyncio.run(scenario())


def test_job_is_private_to_user():
    async def scenario():
        gate = asyncio.Event()

        async def runner(progress):
            await progress("building", 40, "Building")
            await gate.wait()
            return {"ok": True}

        created = await create_build_job(
            user_id="owner",
            runner=runner,
        )
        hidden = await get_build_job(
            user_id="other",
            job_id=created["job_id"],
        )
        assert hidden is None
        await cancel_build_job(
            user_id="owner",
            job_id=created["job_id"],
        )

    asyncio.run(scenario())


def test_cancel_marks_job_cancelled():
    async def scenario():
        gate = asyncio.Event()

        async def runner(progress):
            await progress("building", 25, "Building")
            await gate.wait()
            return {"ok": True}

        created = await create_build_job(
            user_id="u2",
            runner=runner,
        )
        cancelled = await cancel_build_job(
            user_id="u2",
            job_id=created["job_id"],
        )
        assert cancelled is not None
        assert cancelled["status"] == "cancelled"

    asyncio.run(scenario())
