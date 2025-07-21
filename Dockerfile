# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install gcc (needed for some Python packages), and clean up cache for slim image
RUN apt-get update && \
    apt-get install -y gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first and install dependencies (for Docker cache efficiency)
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy entire project code into the container
COPY . .

# Create upload and download folders (as in app config)
RUN mkdir -p /app/static/uploads \
    && mkdir -p /app/static/uploads/documents \
    && mkdir -p /app/static/uploads/proofs \
    && mkdir -p /app/static/downloads

# Expose the app port
EXPOSE 8080

# Use gunicorn for production (multiple workers, better for production)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
