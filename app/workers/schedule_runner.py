"""Celery Beat task: fires due schedules every minute."""
import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.workers.celery_app import celery
from app.db import Schedule, Task, SessionLocal


@celery.task
def tick_schedules():
    asyncio.run(_tick())


async def _tick():
    now = datetime.now(timezone.utc)
    from app.workers.task_worker import execute_task

    async with SessionLocal() as session:
        due = (
            await session.execute(
                select(Schedule)
                .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()

        fired: list[tuple[str, str, str]] = []
        for sched in due:
            task = Task(instruction=sched.instruction, model=sched.model)
            session.add(task)
            await session.flush()
            fired.append((task.id, sched.instruction, sched.model))
            sched.last_run_at = now
            sched.next_run_at = now + timedelta(minutes=sched.interval_minutes)
            sched.run_count += 1

        await session.commit()

    for task_id, instruction, model in fired:
        execute_task.delay(task_id, instruction, model)
