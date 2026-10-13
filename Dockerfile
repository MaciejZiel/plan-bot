# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --extra postgres --extra discord --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --extra postgres --extra discord --no-editable

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 planbot \
    && mkdir /data \
    && chown planbot /data
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/plan-bot.db
USER planbot
WORKDIR /data
VOLUME ["/data"]
ENTRYPOINT ["plan-bot"]
CMD ["run"]
