#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cloudy VPS Bot - one-command start
#
#   ./start.sh          build + start in the background
#   ./start.sh logs     follow the logs
#   ./start.sh stop     stop the bot
#   ./start.sh restart  restart the bot
#   ./start.sh fix      repair the server (permissions, data dir, images)
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose is not installed." >&2
  exit 1
fi

# Older Compose versions require the env file to exist, so create it if missing.
if [[ ! -f .env ]]; then
  echo "==> .env is missing, creating it from .env.example"
  cp .env.example .env
fi

# The bot writes its JSON stores here. A non-writable directory is what caused
# "[Errno 13] Permission denied: '/app'", so make sure it exists and is open.
mkdir -p data
chmod 0777 data 2>/dev/null || true

case "${1:-up}" in
  up)
    echo "==> Building the guest VPS image (ubuntu 22.04)"
    docker build -t "${VPS_IMAGE:-cloudy-vps:ubuntu-22.04}" ./images/ubuntu-22.04
    echo "==> Starting the bot"
    $DC up -d --build
    echo
    $DC ps
    echo
    echo "Done. Follow the logs with: ./start.sh logs"
    ;;
  logs)
    $DC logs -f --tail=100
    ;;
  stop)
    $DC down
    ;;
  restart)
    # NOTE: `docker compose restart` restarts the SAME container and does NOT
    # re-read .env, so edited values were silently ignored and the bot kept
    # using the old settings. Recreate the container instead.
    $DC up -d --force-recreate
    $DC ps
    ;;
  fix)
    bash tools/fix_server.sh
    ;;
  *)
    echo "Usage: ./start.sh [up|logs|stop|restart|fix]" >&2
    exit 1
    ;;
esac
