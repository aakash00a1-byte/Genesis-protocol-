# Genesis Protocol - Production Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./requirements.txt
COPY web/requirements.txt ./web/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt

# Copy application code
COPY genesis_protocol/ ./genesis_protocol/
COPY web/ ./web/
COPY *.py ./
COPY supervisord.conf ./

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV FLASK_APP=web/app.py

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run web server and telegram bot together using supervisord
RUN pip install --no-cache-dir supervisor

# Create log directories
RUN mkdir -p /var/log

CMD ["supervisord", "-c", "/app/supervisord.conf"]