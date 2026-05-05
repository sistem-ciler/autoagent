from celery import Celery
from app.db import settings

celery = Celery(
    "autoagent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.task_worker"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=86400,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
