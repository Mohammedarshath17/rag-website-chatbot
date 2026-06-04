# Use official lightweight Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/models_cache
ENV PORT=8000
ENV HOST=0.0.0.0
ENV RELOAD=False

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling C/C++ packages (like bcrypt, wordcloud)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements first to leverage Docker layer caching
COPY backend/requirements.txt .

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the API port
EXPOSE 8000

# Run the backend FastAPI application
CMD ["python", "-m", "backend.main"]
