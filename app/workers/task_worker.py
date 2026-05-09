"""Celery task: runs Claude in an agentic tool-use loop.

The agent has web_search and web_fetch tools, so it can browse the internet
to research competitors, find market trends, read articles, and gather
real-time information before producing its final answer.

Token tracking accumulates across all turns in the loop.
Prompt caching: the system prompt is marked cache_control=ephemeral.
Rate-limit backoff: 4s, 16s, 64s before giving up.
"""
import asyncio
import time
from datetime import datetime, timezone

import anthropic
from sqlalchemy import update

from app.workers.celery_app import celery
from app.db import Task, TaskStatus, SessionLocal, settings
from app.tools.registry import TOOLS, execute_tool


SYSTEM_PROMPT = """You are autoagent, an AI agent that helps grow businesses.
You have web_search and web_fetch tools — use them to research anything on the internet.

When given a task:
1. Plan your research steps.
2. Search the web for current, real information — do not rely solely on training data.
3. Read relevant pages in full when needed.
4. Synthesize findings into a clear, actionable response with sources cited.

For business tasks: include specific numbers, names, URLs, and sources.
For technical tasks: produce working code, no unnecessary comments.
Always cite sources (URLs) for factual claims."""

MAX_STEPS = 15
_RL_DELAYS = [4, 16, 64]


async def _update(task_id: str, **kwargs) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(updated_at=datetime.now(timezone.utc), **kwargs)
        )
        await session.commit()


def _serialize_blocks(content) -> list[dict]:
    """Convert SDK content block objects to plain dicts for the messages array."""
    out = []
    for b in content:
        if b.type == "thinking":
            out.append({"type": "thinking", "thinking": b.thinking, "signature": b.signature})
        elif b.type == "redacted_thinking":
            out.append({"type": "redacted_thinking", "data": b.data})
        elif b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


@celery.task(bind=True, max_retries=3)
def execute_task(self, task_id: str, instruction: str, model: str = "claude-opus-4-7"):
    t0 = time.time()
    asyncio.run(_update(task_id, status=TaskStatus.running))

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    messages = [{"role": "user", "content": instruction}]
    steps_log: list[str] = []
    total_input = total_output = total_cache = 0

    try:
        final_text = ""

        for step in range(1, MAX_STEPS + 1):
            # Call Claude with rate-limit retry
            rl_attempt = 0
            while True:
                try:
                    response = client.messages.create(
                        model=model,
                        max_tokens=8192,
                        system=[
                            {
                                "type": "text",
                                "text": SYSTEM_PROMPT,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        thinking={"type": "adaptive"},
                        tools=TOOLS,
                        messages=messages,
                    )
                    break
                except anthropic.RateLimitError:
                    if rl_attempt >= len(_RL_DELAYS):
                        raise
                    time.sleep(_RL_DELAYS[rl_attempt])
                    rl_attempt += 1

            # Accumulate tokens across turns
            u = response.usage
            total_input += u.input_tokens
            total_output += u.output_tokens
            total_cache += getattr(u, "cache_read_input_tokens", 0) or 0

            tool_blocks = [b for b in response.content if b.type == "tool_use"]

            if response.stop_reason != "tool_use" or not tool_blocks:
                final_text = "\n".join(b.text for b in response.content if b.type == "text")
                break

            # Append assistant turn (preserves thinking + tool_use blocks)
            messages.append({"role": "assistant", "content": _serialize_blocks(response.content)})

            # Execute tools and collect results
            tool_results = []
            for tc in tool_blocks:
                result = execute_tool(tc.name, tc.input)
                short = result[:600] + ("..." if len(result) > 600 else "")
                call_repr = ", ".join(f'{k}={repr(str(v)[:50])}' for k, v in tc.input.items())
                steps_log.append(f"[Step {step}] {tc.name}({call_repr})\n{short}")
                tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})

            messages.append({"role": "user", "content": tool_results})

        else:
            final_text = "(Agent reached step limit without producing a final answer.)"

        ms = int((time.time() - t0) * 1000)
        result_text = ("\n\n---\n\n".join(steps_log) + "\n\n---\n\n" + final_text) if steps_log else final_text

        asyncio.run(
            _update(
                task_id,
                status=TaskStatus.done,
                result=result_text,
                duration_ms=ms,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_read_tokens=total_cache,
            )
        )

    except anthropic.RateLimitError as exc:
        ms = int((time.time() - t0) * 1000)
        asyncio.run(_update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms))
        raise self.retry(exc=exc, countdown=120)

    except anthropic.APIStatusError as exc:
        ms = int((time.time() - t0) * 1000)
        asyncio.run(_update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms))
        raise self.retry(exc=exc, countdown=30)

    except Exception as exc:
        ms = int((time.time() - t0) * 1000)
        asyncio.run(_update(task_id, status=TaskStatus.failed, error=str(exc), duration_ms=ms))
        raise
