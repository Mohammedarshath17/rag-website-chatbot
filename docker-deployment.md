# Docker Deployment

**Goal**: Containerize the application for portable, reproducible deployment.

## What Was Done
- Created a Dockerfile defining the Python environment and dependencies
- Built a Docker image from the project directory
- Ran the Streamlit application inside a Docker container

## Quick Docker Commands
```bash
# Build the image
docker build -t policynav .

# Run the container (maps container port 8501 to host port 8501)
docker run -p 8501:8501 policynav
```

## Sample Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```
