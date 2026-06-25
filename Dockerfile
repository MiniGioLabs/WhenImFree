FROM python:3.11-slim

WORKDIR /app

# Install uv for fast Python package management
RUN pip install --no-cache-dir uv

# Copy dependency files first (layer caching)
COPY pyproject.toml .
COPY uv.lock* .

# Install deps
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Expose port
EXPOSE 8000

# Run
CMD ["uv", "run", "uvicorn", "calendate.main:app", "--host", "0.0.0.0", "--port", "8000"]
