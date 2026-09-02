#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cloudy VPS Bot 1.3 Beta - server repair script
#
#   bash tools/fix_server.sh          check + repair, then restart the bot
#   bash tools/fix_server.sh --check  only report, change nothing
#
# What it fixes:
#   * "[Errno 13] Permission denied: '/app'"  -> data directory + permissions
#   * stale/removed guest image              -> rebuilds cloudy-vps:ubuntu-22.04
#   * dangling "cloudy-vps-*" containers     -> reports them
#   * missing .env                           -> copies .env.example
#   * docker.sock not reachable              -> clear error message
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/.."

CHECK_ONLY=0
[[ "${1:-}" == "--check" || "${1:-}" == "-n" ]] && CHECK_ONLY=1

GREEN=$'\033[32m'; RED=$'\033[31m'; YEL=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
ok()   { echo "${GREEN}  ok${OFF}   $*"; }
warn() { echo "${YEL} warn${OFF}   $*"; }
bad()  { echo "${RED} fail${OFF}   $*"; }
step() { echo; echo "${DIM}==>${OFF} $*"; }

PROBLEMS=0

step "1/7  Docker"
if ! command -v docker >/dev/null 2>&1; then
  bad "docker is not installed - install Docker Engine first"
  exit 1
fi
if docker info >/dev/null 2>&1; then
  ok "docker daemon is reachable"
else
  bad "cannot talk to the docker daemon (try: sudo systemctl start docker)"
  PROBLEMS=$((PROBLEMS + 1))
fi
if [[ -S /var/run/docker.sock ]]; then
  ok "/var/run/docker.sock exists"
else
  bad "/var/run/docker.sock is missing - the bot cannot create servers"
  PROBLEMS=$((PROBLEMS + 1))
fi

step "2/7  Data directory (the [Errno 13] fix)"
if [[ ! -d data ]]; then
  if (( CHECK_ONLY )); then
    warn "data/ is missing"
  else
    mkdir -p data && ok "created data/"
  fi
else
  ok "data/ exists"
fi
if [[ -d data ]]; then
  if [[ -w data ]]; then
    ok "data/ is writable"
  elif (( CHECK_ONLY )); then
    bad "data/ is NOT writable"
    PROBLEMS=$((PROBLEMS + 1))
  else
    chmod 0777 data 2>/dev/null && ok "opened permissions on data/" || {
      bad "could not chmod data/ - rerun with sudo"
      PROBLEMS=$((PROBLEMS + 1))
    }
  fi
  (( CHECK_ONLY )) || chmod 0666 data/*.json 2>/dev/null || true
fi

step "3/7  .env"
if [[ -f .env ]]; then
  ok ".env is present"
elif (( CHECK_ONLY )); then
  warn ".env is missing (defaults from config.py will be used)"
else
  cp .env.example .env && ok "created .env from .env.example"
fi

step "4/7  Guest image"
IMAGE="${VPS_IMAGE:-cloudy-vps:ubuntu-22.04}"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  ok "$IMAGE is present"
elif (( CHECK_ONLY )); then
  warn "$IMAGE is missing - the first !deploy would have to build it"
else
  echo "     building $IMAGE ..."
  if docker build -t "$IMAGE" ./images/ubuntu-22.04 >/tmp/cloudy-image-build.log 2>&1; then
    ok "built $IMAGE"
  else
    bad "build failed - see /tmp/cloudy-image-build.log"
    PROBLEMS=$((PROBLEMS + 1))
  fi
fi

step "5/7  Guest containers"
RUNNING=$(docker ps --filter "name=cloudy-vps-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$(docker ps -a --filter "name=cloudy-vps-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
ok "$RUNNING running / $TOTAL total guest containers"
DEAD=$(docker ps -a --filter "name=cloudy-vps-" --filter "status=dead" --format '{{.Names}}' 2>/dev/null)
if [[ -n "$DEAD" ]]; then
  warn "dead containers: $DEAD"
  if (( ! CHECK_ONLY )); then
    echo "$DEAD" | xargs -r docker rm -f >/dev/null 2>&1 && ok "removed dead containers"
  fi
fi

step "6/7  Python syntax"
if command -v python3 >/dev/null 2>&1; then
  if python3 -m compileall -q bot.py config.py embeds.py views.py vps_manager.py \
      wallet.py i18n.py slots.py plan_store.py maintenance.py moderation.py \
      token_store.py >/dev/null 2>&1; then
    ok "all modules compile"
  else
    bad "a module failed to compile - run: python3 -m compileall ."
    PROBLEMS=$((PROBLEMS + 1))
  fi
else
  warn "python3 is not installed on the host (fine if you only use Docker)"
fi

step "7/7  Bot container"
if docker ps --format '{{.Names}}' | grep -qx cloudy-vps-bot; then
  ok "cloudy-vps-bot is running"
  if (( ! CHECK_ONLY )); then
    echo "     recreating it so the 1.3 Beta code and .env are picked up ..."
    if docker compose version >/dev/null 2>&1; then
      docker compose up -d --build --force-recreate >/dev/null 2>&1 && ok "restarted"
    else
      docker-compose up -d --build --force-recreate >/dev/null 2>&1 && ok "restarted"
    fi
  fi
else
  warn "cloudy-vps-bot is not running - start it with ./start.sh"
fi

echo
if (( PROBLEMS == 0 )); then
  echo "${GREEN}Server looks healthy.${OFF} Logs: ./start.sh logs"
else
  echo "${RED}${PROBLEMS} problem(s) left.${OFF} Fix them and run this script again."
fi
exit 0
