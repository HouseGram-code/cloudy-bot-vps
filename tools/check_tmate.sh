#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Diagnose "Could not open a tmate session" on the host and inside a guest VPS.
#
#   bash tools/check_tmate.sh                 # host + newest guest container
#   bash tools/check_tmate.sh <container>     # a specific guest container
#
# The bot no longer depends on TCP 2200 only: it probes every port in
# TMATE_PORTS (default 2200,22,443) and uses the first one that connects.
# ---------------------------------------------------------------------------
set -uo pipefail

IMAGE="${VPS_IMAGE:-cloudy-vps:ubuntu-22.04}"
PREFIX="${CONTAINER_PREFIX:-cloudy-vps}"
TMATE_HOST="${TMATE_SERVER_HOST:-ssh.tmate.io}"
PORTS="${TMATE_PORTS:-2200,22,443}"
PORT_LIST="${PORTS//,/ }"

echo "===== HOST ===================================================="
echo "relay host       : $TMATE_HOST"
echo "ports to try     : $PORT_LIST"
echo -n "DNS $TMATE_HOST : "
if getent hosts "$TMATE_HOST" >/dev/null 2>&1; then echo "OK"; else echo "FAILED"; fi
OPEN_HOST=""
for p in $PORT_LIST; do
  printf 'TCP %-5s        : ' "$p"
  BANNER=$(timeout 6 bash -c "exec 3<>/dev/tcp/$TMATE_HOST/$p && head -c 40 <&3" 2>/dev/null)
  if [[ $? -ne 0 ]]; then
    echo "BLOCKED (no outbound route)"
  elif [[ "$BANNER" == SSH-* ]]; then
    echo "OK - real tmate relay"
    OPEN_HOST="$OPEN_HOST $p"
  else
    echo "TCP open but NO SSH banner - not a tmate relay"
  fi
done
if [[ -z "${OPEN_HOST// /}" ]]; then
  echo "!! No real tmate relay is reachable from this host."
  echo "   TCP 2200 is the only true relay port on ssh.tmate.io; 22/443 accept"
  echo "   TCP but send no SSH banner, so the handshake can never complete."
  echo "   'ufw allow out 2200/tcp' does nothing if outbound is already allowed"
  echo "   by default - the block is upstream (provider egress filter)."
  echo "   Either ask the provider to open outbound TCP 2200, or run your own:"
  echo "     RELAY_PORT=443 bash tools/setup_relay.sh"
fi
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
docker exec -e TMATE_HOST="$TMATE_HOST" -e PORT_LIST="$PORT_LIST" "$CONTAINER" bash -lc '
  echo -n "tmate binary     : "; command -v tmate || echo MISSING
  echo -n "tmate version    : "; tmate -V 2>&1 | head -1
  echo -n "DNS $TMATE_HOST : "; getent hosts "$TMATE_HOST" >/dev/null 2>&1 && echo OK || echo FAILED
  for p in $PORT_LIST; do
    printf "TCP %-5s        : " "$p"
    b=$(timeout 6 bash -c "exec 3<>/dev/tcp/$TMATE_HOST/$p && head -c 40 <&3" 2>/dev/null)
    if [ $? -ne 0 ]; then echo "BLOCKED"
    elif echo "$b" | grep -q "^SSH-"; then echo "OK - real tmate relay"
    else echo "TCP open but NO SSH banner - not a tmate relay"; fi
  done
  echo "--- tmate config ---"
  cat /root/.tmate.conf 2>/dev/null || echo "no /root/.tmate.conf yet"
  echo "--- last tmate log ---"
  tail -n 15 /tmp/cloudy.tmate.log 2>/dev/null || echo "no log yet"
'

echo
echo "===== LIVE TEST (fresh session, every port) ==================="
docker exec -e TMATE_HOST="$TMATE_HOST" -e PORT_LIST="$PORT_LIST" "$CONTAINER" bash -lc '
  S=/tmp/diag.tmate.sock
  for p in $PORT_LIST; do
    echo "-- trying $TMATE_HOST:$p"
    pkill -f "tmate -S $S" >/dev/null 2>&1; rm -f $S
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    printf "set -g tmate-server-host %s\nset -g tmate-server-port %s\n" "$TMATE_HOST" "$p" > /tmp/diag.tmate.conf
    nohup tmate -f /tmp/diag.tmate.conf -S $S -F new-session -d "bash -l" > /tmp/diag.tmate.log 2>&1 &
    for i in $(seq 1 8); do
      sleep 2
      OUT=$(tmate -S $S display -p "#{tmate_ssh}" 2>/dev/null)
      case "$OUT" in ssh*) echo "SUCCESS on port $p: $OUT"; exit 0 ;; esac
    done
    echo "   failed on $p"; tail -n 5 /tmp/diag.tmate.log
  done
  echo "FAILED on all ports ($PORT_LIST)"
'
