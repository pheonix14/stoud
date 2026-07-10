FROM python:3.11-slim

# Install system dependencies, including FFmpeg and curl
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . .

# Expose server port
EXPOSE 5000

# Set environment to signal non-debug mode inside container
ENV WERKZEUG_RUN_MAIN=true

# Start server
CMD ["python", "main.py"]
