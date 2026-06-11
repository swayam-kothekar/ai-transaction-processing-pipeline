FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /workspace

# Install system dependencies if any are needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /workspace/
RUN pip install --upgrade pip --default-timeout=60 && \
    pip install --no-cache-dir --default-timeout=60 -r requirements.txt

# Copy application code
COPY . /workspace/

# Expose port 8000
EXPOSE 8000
