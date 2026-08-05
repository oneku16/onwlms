# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.9.21 AS uv

FROM python:3.14-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM builder AS development
RUN uv sync --frozen --all-groups
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]

FROM python:3.14-slim-bookworm AS runtime
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="OwnSIS backend" \
      org.opencontainers.image.revision="$SOURCE_REVISION"
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system --gid 10001 ownsis \
    && useradd --system --uid 10001 --gid ownsis --home-dir /nonexistent ownsis
COPY --from=builder --chown=ownsis:ownsis /app/.venv /app/.venv
COPY --chown=ownsis:ownsis alembic.ini ./
COPY --chown=ownsis:ownsis alembic ./alembic
COPY --chown=ownsis:ownsis src ./src
USER ownsis
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
