# Use Python slim bse image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install required system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \ 
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt . 

#Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy locust files
COPY locustfile.py .

EXPOSE 8080

# Set default host, auth token, and model name
ENV LOCUST_HOST="${LOCUST_HOST}"

CMD ["locust", "--host", "${LOCUST_HOST}", "--web-port", "8080", "--web-host", "0.0.0.0"]
