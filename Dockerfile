FROM python:3.12-slim

# Avoid writing .pyc files and ensure stdout/stderr appear immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System packages required for voice features (libopus/ffmpeg) and crypto libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libsodium-dev \
        libopus0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to leverage Docker layer caching.
COPY packages.pip .
RUN pip install --no-cache-dir -r packages.pip

# Copy the rest of the application code.
COPY . .

# Run command cleanup before starting the bot. Cleanup already syncs commands,
# so the runtime skips the second startup sync.
CMD ["sh", "-c", "python scripts/cleanup_app_commands.py --apply && SYNC_COMMANDS_ON_START=false exec python main.py"]
