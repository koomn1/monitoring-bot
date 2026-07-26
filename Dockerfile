FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg (used by scripts/run_migrations.py, harmless
# at runtime for the main bot process too — kept in the same image so
# `railway run python scripts/run_migrations.py` works out of the box).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY scripts/ ./scripts/

# Railway injects $PORT at runtime; bot/main.py reads it directly
# (see _post_init in bot/main.py). No fixed EXPOSE value is correct
# here since the port is dynamic — Railway detects it automatically.
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot.main"]
