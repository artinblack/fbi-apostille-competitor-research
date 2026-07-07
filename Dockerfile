FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright chromium
RUN apt-get update && apt-get install -y \
    wget curl ca-certificates \
    fonts-liberation libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-xcb1 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libxss1 libxtst6 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium --with-deps

# Copy source
COPY . .

# Create output and cache dirs
RUN mkdir -p output/cache output/screenshots

# Default: run full scan with all extras
CMD ["python", "main.py", "--all-extras", "--notify"]
