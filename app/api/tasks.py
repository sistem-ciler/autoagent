from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Task, get_session

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


@router.post("", status_code=202, response_model=TaskOut)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_session)):
    from app.workers.task_worker import execute_task

    task = Task(instruction=body.instruction, model=body.model)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    execute_task.delay(task.id, task.instruction, task.model)
    return _out(task)


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
