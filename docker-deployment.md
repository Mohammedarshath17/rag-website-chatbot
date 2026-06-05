# Docker Deployment

**Goal**: Containerize the application for portable, reproducible deployment.

## What Was Done
- Created a Dockerfile defining the Python environment and dependencies
- Built a Docker image from the project directory
- Ran the FastAPI application inside a Docker container

## Quick Docker Commands
```bash
# Build the image
docker build -t webrag .

# Run the container (maps container port 8000 to host port 8000)
docker run -p 8000:8000 webrag
```

## Sample Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "backend.main"]
```
