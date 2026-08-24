#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Diagnose "Could not open a tmate session" on the host and inside a guest VPS.
#
#   bash tools/check_tmate.sh                 # host + newest guest container
#   bash tools/check_tmate.sh <container>     # a specific guest container
# ---------------------------------------------------------------------------
set -uo pipefail

IMAGE="${VPS_IMAGE:-cloudy-vps:ubuntu-22.04}"
PREFIX="${CONTAINER_PREFIX:-cloudy-vps}"

echo "===== HOST ===================================================="
echo -n "DNS ssh.tmate.io : "
if getent hosts ssh.tmate.io >/dev/null 2>&1; then echo "OK"; else echo "FAILED"; fi
echo -n "TCP 2200         : "
if timeout 6 bash -c '</dev/tcp/ssh.tmate.io/2200' 2>/dev/null; then echo "OK"; else echo "BLOCKED (open outbound TCP 2200 in your firewall)"; fi
echo -n "Guest image      : "
if docker image inspect "$IMAGE" >/dev/null 2>&1; then echo "$IMAGE present"; else echo "MISSING - run: docker build -t $IMAGE ./images/ubuntu-22.04"; fi

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo -n "tmate in image   : "
  docker run --rm --entrypoint sh "$IMAGE" -c 'tmate -V 2>/dev/null || echo "NOT INSTALLED"' 2>/dev/null || echo "could not check"
fi

CONTAINER="${1:-$(docker ps --filter "name=${PREFIX}-" --format '{{.Names}}' | head -1)}"
if [[ -z "$CONTAINER" ]]; then
  echo
  echo "No running guest VPS found. Deploy one with !deploy, then re-run this script."
  exit 0
fi

echo
echo "===== GUEST: $CONTAINER ======================================"
docker exec "$CONTAINER" bash -lc '
  echo -n "tmate binary     : "; command -v tmate || echo MISSING
  echo -n "tmate version    : "; tmate -V 2>&1 | head -1
  echo -n "DNS ssh.tmate.io : "; getent hosts ssh.tmate.io >/dev/null 2>&1 && echo OK || echo FAILED
  echo -n "TCP 2200         : "; timeout 6 bash -c "</dev/tcp/ssh.tmate.io/2200" 2>/dev/null && echo OK || echo BLOCKED
  echo "--- last tmate log ---"
  tail -n 15 /tmp/cloudy.tmate.log 2>/dev/null || echo "no log yet"
'

echo
echo "===== LIVE TEST (fresh session) =============================="
docker exec "$CONTAINER" bash -lc '
  S=/tmp/diag.tmate.sock
  pkill -f "tmate -S $S" >/dev/null 2>&1; rm -f $S
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  nohup tmate -S $S -F new-session -d "bash -l" > /tmp/diag.tmate.log 2>&1 &
  for i in $(seq 1 20); do
    sleep 2
    OUT=$(tmate -S $S display -p "#{tmate_ssh}" 2>/dev/null)
    case "$OUT" in ssh*) echo "SUCCESS: $OUT"; exit 0 ;; esac
  done
  echo "FAILED - tmate log:"; tail -n 20 /tmp/diag.tmate.log
'
