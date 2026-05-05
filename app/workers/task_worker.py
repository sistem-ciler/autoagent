"""Celery task that runs Claude with prompt caching + rate-limit backoff.

Prompt caching: the system prompt is marked cache_control=ephemeral.  Anthropic
caches any prefix >= ~1 k tokens for 5 minutes; repeated calls to the same
model with the same system prompt pay only the tiny cache-read rate instead of
full input tokens — typically 10-20x cheaper and counts far less against TPM.

Rate-limit backoff: on anthropic.RateLimitError we sleep 4s, 16s, 64s before
giving up, so transient bursts don't cascade into permanent failures.
"""
import asyncio
import time
from datetime import datetime, timezone

import anthropic
from sqlalchemy import update

from app.workers.celery_app import celery
from app.db import Task, TaskStatus, SessionLocal, settings


SYSTEM_PROMPT = """You are autoagent, a highly capable task-completion AI.
You reason carefully, plan step by step, and produce clear, correct output.
For coding tasks: prefer idiomatic, minimal solutions with no unnecessary comments.
For analysis tasks: be concise, evidence-based, and actionable."""


async def _update(task_id: str, **kwargs) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(updated_at=datetime.now(timezone.utc), **kwargs)
        )
        await session.commit()


@celery.task(bind=True, max_retries=3)
def execute_task(self, task_id: str, instruction: str, model: str = "claude-opus-4-7"):
    t0 = time.time()
    asyncio.run(_update(task_id, status=TaskStatus.running))

    # Exponential backoff delays for rate-limit retries (seconds)
    _rl_delays = [4, 16, 64]

    attempt = 0
    while True:
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

            with client.messages.stream(
                model=model,
                max_tokens=8192,
                # System prompt with cache_control — Anthropic caches this prefix
                # so subsequent calls with the same system prompt are ~10x cheaper
                # on input tokens and count far less against rate limits.
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": instruction}],
            ) as stream:
                final = stream.get_final_message()

            text = "\n".join(b.text for b in final.content if b.type == "text")
            usage = final.usage
            ms = int((time.time() - t0) * 1000)

            asyncio.run(
                _update(
                    task_id,
                    status=TaskStatus.done,
                    result=text,
                    duration_ms=ms,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
                )
            )
            return

        except anthropic.RateLimitError as exc:
            if attempt >= len(_rl_delays):
                ms = int((time.time() - t0) * 1000)
                asyncio.run(
                    _update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms)
                )
                raise self.retry(exc=exc, countdown=120)
            delay = _rl_delays[attempt]
            attempt += 1
            time.sleep(delay)

        except anthropic.APIStatusError as exc:
            ms = int((time.time() - t0) * 1000)
            asyncio.run(
                _update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms)
            )
            raise self.retry(exc=exc, countdown=30)

        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            asyncio.run(
                _update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms)
            )
            raise
