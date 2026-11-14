# Multi-stage Dockerfile for VendOps Unified Single-Image Deployment
FROM python:3.12-slim AS builder

WORKDIR /app

ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
ENV HF_HUB_DISABLE_IMPLICIT_TOKEN=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy project source and references
COPY src/ ./src/
COPY vendor/ ./vendor/
COPY evals/ ./evals/
COPY README.md AGENTS.md ./

# Install project into virtualenv
RUN uv sync --frozen

# Pre-download FastEmbed multilingual model into image cache for offline execution
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# --- Runtime Stage ---
FROM python:3.12-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
ENV HF_HUB_DISABLE_IMPLICIT_TOKEN=1

EXPOSE 8000 8001

CMD ["uv", "run", "uvicorn", "vendops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
