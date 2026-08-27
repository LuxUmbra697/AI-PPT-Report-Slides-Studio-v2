FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv run python scripts/fetch_fonts.py || true

EXPOSE 39800
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
