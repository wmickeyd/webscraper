FROM python:3.12-slim

# Install system dependencies, Chromium, and Chromium Driver
# Debian-based slim images use 'chromium' and 'chromium-driver'
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY scraper.py .

# Set environment variables for Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/

# Expose the port the app runs on
EXPOSE 8000

# Run the application
CMD ["python", "scraper.py", "serve"]
