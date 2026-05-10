from celery import Celery

from app.db import settings

celery = Celery(
    "autoagent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.task_worker", "app.workers.schedule_runner"],
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "tick-schedules": {
            "task": "app.workers.schedule_runner.tick_schedules",
            "schedule": 60.0,
        }
    },
)
