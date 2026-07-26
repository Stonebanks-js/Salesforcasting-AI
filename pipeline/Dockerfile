FROM python:3.11-slim

# Java is required by Spark (local mode).
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
# Nightly batch: run once then exit (scheduling via docker restart or cron).
CMD ["python", "nightly.py"]
