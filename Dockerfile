FROM node:18 AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM python:3.10-slim
WORKDIR /app

# Install FFmpeg and Git
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files
COPY . .

# Copy built frontend
COPY --from=frontend-build /app/dist ./dist

# Git config
RUN git config --global user.email "stoud@bot.com" && \
    git config --global user.name "Stoud Bot"

EXPOSE 8000

# Start server (Uvicorn watchdog handles reload locally, but we just run main.py here)
CMD ["python", "main.py"]
