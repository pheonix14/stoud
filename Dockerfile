FROM python:3.11-slim

# Install system dependencies: FFmpeg for video streaming, curl for health checks, procps for memory inspection
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose default port
EXPOSE 5000

# Configure environment for Render free tier limits
ENV PYTHONUNBUFFERED=1
ENV WERKZEUG_RUN_MAIN=true
ENV MALLOC_ARENA_MAX=2
ENV STOUD_RAM_LIMIT_MB=450
ENV STOUD_SHARD_DURATION=1800

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-5000}/api/health || exit 1

# Start production gunicorn with gthread worker
CMD ["sh", "-c", "gunicorn --worker-class gthread --workers 1 --threads 4 --timeout 120 --keep-alive 5 -b 0.0.0.0:${PORT:-5000} main:app"]
