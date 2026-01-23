# Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-interaction --no-ansi --no-root

# Copy code
COPY agent/ ./agent/
COPY prompts/ ./prompts/
COPY iris_api.py .
COPY iris_frontend.html .
COPY .env.example .env

EXPOSE 8000

# Run the API
CMD ["uvicorn", "iris_api:app", "--host", "0.0.0.0", "--port", "8000"]
