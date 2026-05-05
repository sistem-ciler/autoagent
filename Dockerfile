FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
RUN uv pip install --system \
    "anthropic>=0.49.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "celery[redis]>=5.4.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.30.0" \
    "pydantic-settings>=2.7.0" \
    "python-dotenv>=1.0.0"

FROM deps AS final
COPY app/ ./app/
COPY agent.py agent-claude.py ./

RUN ln -sf $(which python3) /usr/local/bin/python
RUN mkdir -p /logs /app/output

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
