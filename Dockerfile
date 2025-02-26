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
COPY . .

EXPOSE 8089

ENV CHAT_MODEL=bedrock_claude_haiku35_pipeline_mock
ENV USER_PROMPT="Hi Mock bot, give me a poem"
ENV CONTENT_VALIDATION_STRING="unravel"
ENV GSA_AUTH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMxMDIyNDc0LTAxYjItNDBjOS1hZjI5LTE0NTAyMDg3Y2MxNiJ9.ZGpZQSesisUyeKg8sE92v_oyX2uKTjlHM_On8f9qHlg"
ENV SESSION="eyJvYXV0aDJfc3RhdGUiOiAiRmRMeTZiUXJycmY4S05jWGItMTZtUSJ9.Z43x1A.IPBcsUda5gUS2-rwLq2AtVmn6dw"
ENV GSAI_HOST=http://0.0.0.0:8080
ENV CUSTOM_CSV_FILE_PATH=custom_metrics.csv

# Set default host, auth token, and model name
ARG LOCUST_HOST="http://0.0.0.0:8080"
ENV LOCUST_HOST=${LOCUST_HOST}

CMD locust --host "${LOCUST_HOST}" --web-port 8089 --web-host 0.0.0.0
