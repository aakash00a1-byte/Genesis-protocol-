# Genesis Protocol Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY genesis_protocol/ ./genesis_protocol/
COPY .env.example .env 2>/dev/null || true

# Create data directory
RUN mkdir -p ./data/chroma_db

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

# Default command - run the bot
CMD ["python3", "-m", "genesis_protocol.main"]