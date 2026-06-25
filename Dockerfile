FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras, frozen)
RUN uv sync --frozen --no-dev

# Copy source AFTER deps so local package gets installed on next step
COPY src/ ./src/

# Re-sync to install the local package
RUN uv sync --frozen --no-dev

# Non-root user
ENV UV_CACHE_DIR=/tmp/uv-cache
RUN useradd -r -s /bin/false appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "calendate.main:app", "--host", "0.0.0.0", "--port", "8000"]
