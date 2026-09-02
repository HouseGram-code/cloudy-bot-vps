# Cloudy VPS Bot v1.3 Beta
FROM python:3.12-slim

# DATA_DIR is where every JSON store lives (state, wallet, bans, languages...).
# config.py falls back to a writable directory automatically, but setting it
# here keeps the data on the mounted volume.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI (handy for debugging inside the bot container)
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz \
      -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fix for: Deployment failed: [Errno 13] Permission denied: '/app'
# The data directory is created at build time and made writable for any UID,
# so the bot can persist state even when the container runs as a non-root user
# or when ./data is bind-mounted from a host directory owned by someone else.
RUN mkdir -p /app/data && chmod 0777 /app /app/data

CMD ["python", "bot.py"]
