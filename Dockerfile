# Dockerfile for Repo2Product AI on Hugging Face Spaces
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# This triggers "Cloud Mode" in our orchestrator
ENV R2P_CLOUD 1

# Set working directory
WORKDIR /app

# Install system dependencies (git for local dev fallback, though we use API)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create output directory and set permissions (though we use /tmp in cloud mode)
RUN mkdir -p /app/output && chmod 777 /app/output

# Hugging Face Spaces default port is 7860
EXPOSE 7860

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port", "7860", "--server.address", "0.0.0.0"]
