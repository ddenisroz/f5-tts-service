FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md alembic.ini /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic /app/alembic
COPY app /app/app
COPY data /app/data
COPY models /app/models
COPY scripts /app/scripts
COPY vendor /app/vendor

EXPOSE 8011

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
