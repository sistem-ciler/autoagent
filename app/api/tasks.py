from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Task, TaskStatus, get_session

router = APIRouter()


class TaskCreate(BaseModel):
    instruction: str
    model: str = "claude-opus-4-7"


class TaskOut(BaseModel):
    id: str
    status: str
    instruction: str
    model: str
    result: str | None
    error: str | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    total: int
    by_status: dict[str, int]
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    tasks: list[TaskOut]


@router.post("", status_code=202, response_model=TaskOut)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_session)):
    from app.workers.task_worker import execute_task

    task = Task(instruction=body.instruction, model=body.model)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    execute_task.delay(task.id, task.instruction, task.model)
    return _out(task)


@router.get("", response_model=TaskListOut)
async def list_tasks(
    db: AsyncSession = Depends(get_session),
    status: TaskStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(Task).order_by(desc(Task.created_at)).limit(limit).offset(offset)
    if status is not None:
        q = q.where(Task.status == status)
    rows = (await db.execute(q)).scalars().all()

    by_status_q = select(Task.status, func.count()).group_by(Task.status)
    by_status_rows = (await db.execute(by_status_q)).all()
    by_status = {s.value: c for s, c in by_status_rows}

    totals_q = select(
        func.coalesce(func.sum(Task.input_tokens), 0),
        func.coalesce(func.sum(Task.output_tokens), 0),
        func.coalesce(func.sum(Task.cache_read_tokens), 0),
    )
    totals = (await db.execute(totals_q)).one()

    return TaskListOut(
        total=sum(by_status.values()),
        by_status=by_status,
        total_input_tokens=int(totals[0]),
        total_output_tokens=int(totals[1]),
        total_cache_read_tokens=int(totals[2]),
        tasks=[_out(r) for r in rows],
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session)):
    row = (
        await db.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    return _out(row)


def _out(t: Task) -> TaskOut:
    return TaskOut(
        id=t.id,
        status=t.status.value,
        instruction=t.instruction,
        model=t.model,
        result=t.result,
        error=t.error,
        duration_ms=t.duration_ms,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        cache_read_tokens=t.cache_read_tokens,
        created_at=t.created_at.isoformat(),
        updated_at=t.updated_at.isoformat(),
    )
