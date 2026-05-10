from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Schedule, get_session

router = APIRouter()


class ScheduleCreate(BaseModel):
    name: str
    instruction: str
    model: str = "claude-opus-4-7"
    interval_minutes: int = 1440
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    instruction: str | None = None
    model: str | None = None
    interval_minutes: int | None = None
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: str
    name: str
    instruction: str
    model: str
    interval_minutes: int
    enabled: bool
    last_run_at: str | None
    next_run_at: str
    run_count: int
    created_at: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Schedule).order_by(Schedule.created_at))).scalars().all()
    return [_out(r) for r in rows]


@router.post("", status_code=201, response_model=ScheduleOut)
async def create_schedule(body: ScheduleCreate, db: AsyncSession = Depends(get_session)):
    s = Schedule(
        name=body.name,
        instruction=body.instruction,
        model=body.model,
        interval_minutes=body.interval_minutes,
        enabled=body.enabled,
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=body.interval_minutes),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _out(s)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: str, body: ScheduleUpdate, db: AsyncSession = Depends(get_session)
):
    row = (
        await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="schedule not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_session)):
    row = (
        await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="schedule not found")
    await db.delete(row)
    await db.commit()


def _out(s: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        name=s.name,
        instruction=s.instruction,
        model=s.model,
        interval_minutes=s.interval_minutes,
        enabled=s.enabled,
        last_run_at=s.last_run_at.isoformat() if s.last_run_at else None,
        next_run_at=s.next_run_at.isoformat(),
        run_count=s.run_count,
        created_at=s.created_at.isoformat(),
    )
