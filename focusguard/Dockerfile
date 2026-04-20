ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:13.0.0
FROM $BUILD_FROM

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend /app/backend
COPY dashboard /app/dashboard
COPY config.yaml /app/config.yaml

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh
