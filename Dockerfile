# Genesis Protocol - Web Dockerfile
# For Render Native Python Runtime

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY web/requirements.txt /app/web/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/web/requirements.txt

# Copy web application
COPY web/ /app/web/

# Create session directory
RUN mkdir -p /tmp/flask_session

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV SESSION_TYPE=filesystem

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app_v3:app"]