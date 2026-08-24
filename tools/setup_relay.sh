#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run your OWN tmate relay (tmate-ssh-server) on this host.
#
# Use this when ssh.tmate.io:2200 is blocked outbound and only ports like
# 22/443 are open: those ports on ssh.tmate.io are NOT the tmate relay, so
# tmate can never complete its handshake there. A self-hosted relay lets you
# pick the port yourself.
#
#   bash tools/setup_relay.sh                 # relay on port 443
#   RELAY_PORT=8443 bash tools/setup_relay.sh # relay on another port
#   RELAY_HOST=vps.example.com bash tools/setup_relay.sh
#
# At the end the script prints the TMATE_* lines for .env and can append them
# automatically.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

RELAY_PORT="${RELAY_PORT:-443}"
RELAY_NAME="${RELAY_NAME:-cloudy-tmate-relay}"
KEYS_DIR="${KEYS_DIR:-$PWD/data/tmate-keys}"
IMAGE="${RELAY_IMAGE:-tmate/tmate-ssh-server:latest}"

# Public address that end users will SSH to. Auto-detected if not given.
RELAY_HOST="${RELAY_HOST:-}"
if [[ -z "$RELAY_HOST" ]]; then
  RELAY_HOST="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
fi
if [[ -z "$RELAY_HOST" ]]; then
  echo "Could not auto-detect the public address. Re-run with RELAY_HOST=<ip|domain>." >&2
  exit 1
fi

echo "==> relay host : $RELAY_HOST"
echo "==> relay port : $RELAY_PORT"
echo "==> keys dir   : $KEYS_DIR"

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${RELAY_PORT}\$"; then
  echo "!! Port $RELAY_PORT is already in use on this host. Pick another with RELAY_PORT=..." >&2
  exit 1
fi

mkdir -p "$KEYS_DIR"
docker pull "$IMAGE"

# Host keys for the relay (generated once, reused afterwards).
if [[ ! -f "$KEYS_DIR/ssh_host_ed25519_key" ]]; then
  echo "==> generating relay host keys"
  docker run --rm -v "$KEYS_DIR:/keys" --entrypoint /bin/sh "$IMAGE" \
    -c 'create_keys.sh /keys >/dev/null 2>&1 || /usr/bin/create_keys.sh /keys'
fi

docker rm -f "$RELAY_NAME" >/dev/null 2>&1 || true
docker run -d --name "$RELAY_NAME" \
  --restart unless-stopped \
  --cap-add SYS_ADMIN \
  -p "${RELAY_PORT}:${RELAY_PORT}" \
  -v "$KEYS_DIR:/etc/tmate-ssh-server-keys" \
  "$IMAGE" \
  -h "$RELAY_HOST" -p "$RELAY_PORT" -k /etc/tmate-ssh-server-keys >/dev/null

echo "==> waiting for the relay to come up"
sleep 5
docker logs "$RELAY_NAME" 2>&1 | tail -n 20 || true

# tmate prints the fingerprints it expects clients to pin.
RSA_FP="$(docker logs "$RELAY_NAME" 2>&1 | grep -oE 'SHA256:[A-Za-z0-9+/=]+' | head -1 || true)"
ED_FP="$(docker logs "$RELAY_NAME" 2>&1 | grep -oE 'SHA256:[A-Za-z0-9+/=]+' | sed -n 2p || true)"

if [[ -z "$RSA_FP" ]]; then
  # Fall back to computing them from the key files.
  RSA_FP="$(ssh-keygen -lf "$KEYS_DIR/ssh_host_rsa_key.pub" 2>/dev/null | awk '{print $2}')"
  ED_FP="$(ssh-keygen -lf "$KEYS_DIR/ssh_host_ed25519_key.pub" 2>/dev/null | awk '{print $2}')"
fi

echo
echo "===== ADD THESE LINES TO .env ================================="
cat <<EOF
TMATE_SERVER_HOST=$RELAY_HOST
TMATE_PORTS=$RELAY_PORT
TMATE_RSA_FINGERPRINT=$RSA_FP
TMATE_ED25519_FINGERPRINT=$ED_FP
EOF
echo "==============================================================="
echo
read -r -p "Append them to .env now? [y/N] " ans
if [[ "${ans:-n}" =~ ^[Yy]$ ]]; then
  [[ -f .env ]] || cp .env.example .env
  sed -i '/^TMATE_SERVER_HOST=/d;/^TMATE_PORTS=/d;/^TMATE_RSA_FINGERPRINT=/d;/^TMATE_ED25519_FINGERPRINT=/d' .env
  {
    echo "TMATE_SERVER_HOST=$RELAY_HOST"
    echo "TMATE_PORTS=$RELAY_PORT"
    echo "TMATE_RSA_FINGERPRINT=$RSA_FP"
    echo "TMATE_ED25519_FINGERPRINT=$ED_FP"
  } >> .env
  echo "==> .env updated. Restart the bot:  ./start.sh restart"
else
  echo "==> nothing written. Copy the lines above into .env, then ./start.sh restart"
fi

echo
echo "Note: open inbound TCP $RELAY_PORT in your firewall/provider panel,"
echo "      e.g. sudo ufw allow ${RELAY_PORT}/tcp"
