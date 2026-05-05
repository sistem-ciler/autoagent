import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.db import init_db
from app.api import tasks as tasks_router

_START = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="autoagent", version="0.1.0", lifespan=lifespan)
app.include_router(tasks_router.router, prefix="/tasks")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "autoagent", "ts": int(time.time() * 1000)}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    import resource

    uptime = time.time() - _START
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    return (
        "# HELP autoagent_up Service availability\n"
        "# TYPE autoagent_up gauge\n"
        "autoagent_up 1\n"
        "# HELP autoagent_uptime_seconds Seconds since start\n"
        "# TYPE autoagent_uptime_seconds counter\n"
        f"autoagent_uptime_seconds {uptime:.1f}\n"
        "# HELP process_resident_memory_bytes Resident memory\n"
        "# TYPE process_resident_memory_bytes gauge\n"
        f"process_resident_memory_bytes {rss}\n"
    )
