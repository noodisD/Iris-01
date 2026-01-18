# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed for building C-extensions (like hdbscan)
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  gcc \
  && rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtual environment
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
  && poetry install --only=main --no-interaction --no-ansi --no-root

# --- Stage 2: Runtime ---
FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  ANONYMIZED_TELEMETRY=False \
  PYTHONWARNINGS=ignore::DeprecationWarning

WORKDIR /app
# Create a non-root user for security
RUN groupadd -r irisgroup && useradd -r -g irisgroup irisuser

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY agent/ ./agent/
COPY prompts/ ./prompts/
COPY companion.py .

# Create data directory and set permissions
# RUN mkdir /data && chown -R irisuser:irisgroup /app && chmod +x companion.py
VOLUME /data

# Switch to non-root user
# USER irisuser

# Health check (just check if container is running)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD echo "healthy" || exit 1

# Keep container running (don't run the interactive CLI in Docker)
# The API on the host machine will import and use the companion modules as needed
ENTRYPOINT ["tail", "-f", "/dev/null"]
