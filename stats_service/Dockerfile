FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1003 flaskuser && \
    chown -R flaskuser:flaskuser /app
USER flaskuser

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl --fail http://localhost:5001/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5001", \
    "--workers", "2", \
    "--threads", "4", \
    "--worker-class", "sync", \
    "--timeout", "120", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "app:app"]