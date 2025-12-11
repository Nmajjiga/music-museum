FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user
RUN useradd -m -u 1002 flaskuser && \
    chown -R flaskuser:flaskuser /app
USER flaskuser

EXPOSE 5002

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:5002/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5002", \
    "--workers", "2", \
    "--threads", "4", \
    "--worker-class", "sync", \
    "--timeout", "120", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "app:app"]