FROM python:3.11-slim

WORKDIR /app

# Install dependencies and tzdata for timezone support
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend /app/backend
COPY dashboard /app/dashboard
COPY app_config.yaml /app/config.yaml

# Run uvicorn directly as PID 1
CMD ["python3", "-u", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
