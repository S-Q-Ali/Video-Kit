FROM python:3.11-slim

WORKDIR /app

# Install system deps: FFmpeg, build tools for Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create download directory
RUN mkdir -p downloads

EXPOSE ${PORT:-8000}

CMD gunicorn --bind 0.0.0.0:${PORT:-8000} \
    --workers 1 \
    --threads 4 \
    --timeout 300 \
    --worker-class gthread \
    main:app