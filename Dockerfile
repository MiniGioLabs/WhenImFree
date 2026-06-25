FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras, frozen)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/

# Non-root user
RUN useradd -r -s /bin/false appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "calendate.main:app", "--host", "0.0.0.0", "--port", "8000"]
