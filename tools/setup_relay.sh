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

# Public address that guests will SSH to.
#
# WARNING: an "echo my IP" service reports the address of whatever NAT gateway
# or proxy your egress traffic exits through. On a NATed / proxied host that
# address belongs to someone else entirely, and pointing the bot at it gives
# "Connection refused". So we auto-detect only as a hint and VERIFY the address
# afterwards against the running relay.
RELAY_HOST="${RELAY_HOST:-}"
RELAY_HOST_GIVEN=0
[[ -n "$RELAY_HOST" ]] && RELAY_HOST_GIVEN=1

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

# Port check. Our OWN relay from a previous run holds this port, and that is
# fine - we recreate it below. Only a foreign listener is a real conflict.
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${RELAY_PORT}\$"; then
  if [[ "$(docker inspect -f '{{.State.Running}}' "$RELAY_NAME" 2>/dev/null)" == "true" ]]; then
    echo "==> port $RELAY_PORT is held by our own relay ($RELAY_NAME) - recreating it"
    docker rm -f "$RELAY_NAME" >/dev/null 2>&1 || true
    sleep 1
  else
    echo "!! Port $RELAY_PORT is already in use by another process:" >&2
    ss -ltnp 2>/dev/null | grep -E "[:.]${RELAY_PORT}\b" >&2 || true
    echo "   Free it, or pick another port with RELAY_PORT=..." >&2
    exit 1
  fi
fi

mkdir -p "$KEYS_DIR"
docker pull "$IMAGE"

# Host keys for the relay (generated once, reused afterwards).
#
# NOTE: the tmate/tmate-ssh-server image does NOT ship create_keys.sh, so the
# old call failed with "/usr/bin/create_keys.sh: not found" and, under `set -e`,
# aborted the whole script before the relay was ever started. Generate the two
# host keys ourselves with ssh-keygen instead.
gen_keys() {
  if command -v ssh-keygen >/dev/null 2>&1; then
    ssh-keygen -q -t rsa -b 2048 -N "" -f "$KEYS_DIR/ssh_host_rsa_key"
    ssh-keygen -q -t ed25519      -N "" -f "$KEYS_DIR/ssh_host_ed25519_key"
  else
    # No ssh-keygen on the host - borrow one from a throwaway container.
    docker run --rm -v "$KEYS_DIR:/keys" --entrypoint /bin/sh alpine:3 -c '
      apk add --no-cache openssh-keygen >/dev/null 2>&1 || apk add --no-cache openssh >/dev/null 2>&1
      ssh-keygen -q -t rsa -b 2048 -N "" -f /keys/ssh_host_rsa_key
      ssh-keygen -q -t ed25519      -N "" -f /keys/ssh_host_ed25519_key
    '
  fi
}

if [[ ! -f "$KEYS_DIR/ssh_host_ed25519_key" || ! -f "$KEYS_DIR/ssh_host_rsa_key" ]]; then
  echo "==> generating relay host keys"
  rm -f "$KEYS_DIR"/ssh_host_rsa_key* "$KEYS_DIR"/ssh_host_ed25519_key*
  gen_keys
fi

if [[ ! -f "$KEYS_DIR/ssh_host_ed25519_key" || ! -f "$KEYS_DIR/ssh_host_rsa_key" ]]; then
  echo "!! Could not generate the relay host keys in $KEYS_DIR" >&2
  echo "   Install openssh-client (sudo apt-get install -y openssh-client) and retry." >&2
  exit 1
fi
chmod 600 "$KEYS_DIR"/ssh_host_rsa_key "$KEYS_DIR"/ssh_host_ed25519_key

docker rm -f "$RELAY_NAME" >/dev/null 2>&1 || true

# NOTE: this image is driven by ENVIRONMENT VARIABLES, not by CLI flags.
# Passing `-h/-p/-k` sends them to the image entrypoint, which does not
# understand them: it printed "sh: out of range" and then started the server
# with no key path at all, hence
#   "fatal: Error listening to socket: ECDSA, ED25519, DSA, or RSA host key
#    file must be set".
# SSH_KEYS_PATH / SSH_HOSTNAME / SSH_PORT_LISTEN are the supported knobs.
# --network host instead of -p: the relay then binds the host's own addresses,
# so the guest containers reach it without any Docker NAT hairpin (that is what
# used to give "Connection refused" from inside a VPS while 127.0.0.1 was fine).
docker run -d --name "$RELAY_NAME" \
  --restart unless-stopped \
  --cap-add SYS_ADMIN \
  --network host \
  -v "$KEYS_DIR:/etc/tmate-ssh-server-keys" \
  -e SSH_KEYS_PATH=/etc/tmate-ssh-server-keys \
  -e SSH_HOSTNAME="$RELAY_HOST" \
  -e SSH_PORT_LISTEN="$RELAY_PORT" \
  -e SSH_PORT="$RELAY_PORT" \
  "$IMAGE" >/dev/null

# Probe an SSH endpoint properly.
#
# IMPORTANT: tmate-ssh-server does NOT send its banner first - it waits for the
# client identification string. A read-only probe therefore always times out on
# a perfectly healthy relay (that is why the previous check failed even though
# the log said "Accepting connections on :443"). We must write our own version
# string before reading.
ssh_probe() {  # ssh_probe <host> <port> -> prints banner, empty when none
  local h="$1" p="$2"
  timeout 8 bash -c "
    exec 3<>/dev/tcp/$h/$p || exit 1
    printf 'SSH-2.0-cloudy_probe\\r\\n' >&3
    head -c 60 <&3
  " 2>/dev/null || true
}

echo "==> waiting for the relay to come up"
RELAY_UP=0
for _ in $(seq 1 15); do
  sleep 2
  if [[ "$(docker inspect -f '{{.State.Running}}' "$RELAY_NAME" 2>/dev/null)" != "true" ]]; then
    continue
  fi
  # Running is not enough: a crash-looping container is "running" between
  # restarts. An SSH banner proves the relay actually serves the port.
  B="$(ssh_probe 127.0.0.1 "$RELAY_PORT")"
  if [[ "$B" == SSH-* ]]; then
    RELAY_UP=1
    echo "==> relay banner: ${B%%$'\r'*}"
    break
  fi
done

docker logs "$RELAY_NAME" 2>&1 | tail -n 20 || true

if [[ "$RELAY_UP" -ne 1 ]]; then
  echo >&2
  echo "!! The relay never answered with an SSH banner on port $RELAY_PORT." >&2
  echo "   Full relay log:" >&2
  docker logs "$RELAY_NAME" 2>&1 | tail -n 40 >&2 || true
  echo >&2
  echo "   Nothing was written to .env, so the bot keeps its current settings." >&2
  exit 1
fi
echo "==> relay is up and serving SSH on $RELAY_PORT"

# Fingerprints that tmate clients pin. Compute them from the key files: that is
# authoritative, while the relay log format changes between image versions.
RSA_FP="$(ssh-keygen -l -E sha256 -f "$KEYS_DIR/ssh_host_rsa_key.pub" 2>/dev/null | awk '{print $2}')"
ED_FP="$(ssh-keygen -l -E sha256 -f "$KEYS_DIR/ssh_host_ed25519_key.pub" 2>/dev/null | awk '{print $2}')"

if [[ -z "$RSA_FP" || -z "$ED_FP" ]]; then
  # Last resort: scrape whatever the relay printed.
  RSA_FP="${RSA_FP:-$(docker logs "$RELAY_NAME" 2>&1 | grep -oE 'SHA256:[A-Za-z0-9+/=]+' | head -1 || true)}"
  ED_FP="${ED_FP:-$(docker logs "$RELAY_NAME" 2>&1 | grep -oE 'SHA256:[A-Za-z0-9+/=]+' | sed -n 2p || true)}"
fi

# ---------------------------------------------------------------------------
# Verify that $RELAY_HOST really points at THIS relay.
#
# The relay is confirmed working on 127.0.0.1 by now. If the same port on
# $RELAY_HOST does not answer with the tmate banner, that address is not us -
# writing it into .env would only produce "Connection refused" in the bot.
# ---------------------------------------------------------------------------
echo -n "==> checking that $RELAY_HOST:$RELAY_PORT reaches this relay : "
PUB="$(ssh_probe "$RELAY_HOST" "$RELAY_PORT")"
if [[ "$PUB" == SSH-* ]]; then
  echo "OK"
else
  echo "UNREACHABLE"
  echo
  echo "!! $RELAY_HOST does not reach the relay running on this host." >&2
  if [[ "$RELAY_HOST_GIVEN" -eq 0 ]]; then
    echo "   That address came from api.ipify.org, which reports the NAT gateway" >&2
    echo "   or proxy your traffic exits through - not necessarily your server." >&2
  fi
  echo >&2
  echo "   Addresses actually bound on this host:" >&2
  ip -4 addr show scope global 2>/dev/null | awk '/inet /{print "     " $2}' >&2 || true
  echo >&2
  echo "   Re-run with an address your guests can reach, e.g.:" >&2
  echo "     RELAY_HOST=<public-ip-or-domain> RELAY_PORT=$RELAY_PORT bash tools/setup_relay.sh" >&2
  echo >&2
  echo "   Also confirm inbound TCP $RELAY_PORT is open in your provider panel" >&2
  echo "   (AWS security group / firewall), not just in ufw." >&2
  echo >&2
  echo "   Nothing was written to .env, so the bot keeps its current settings." >&2
  exit 1
fi

# The bot reads data/relay.json at start-up (and `!relay` writes the same
# file), so the relay is picked up even if nobody ever edits .env.
mkdir -p data
cat > data/relay.json <<EOF
{
  "ed25519": "$ED_FP",
  "guest_ok": true,
  "host": "$RELAY_HOST",
  "port": $RELAY_PORT,
  "rsa": "$RSA_FP",
  "updated": $(date +%s)
}
EOF
chmod 0666 data/relay.json 2>/dev/null || true
echo "==> wrote data/relay.json - the bot uses it as-is after a restart"

echo
echo "===== ADD THESE LINES TO .env ================================="
cat <<EOF
PUBLIC_HOST=$RELAY_HOST
TMATE_SERVER_HOST=$RELAY_HOST
TMATE_PORTS=$RELAY_PORT
TMATE_RSA_FINGERPRINT=$RSA_FP
TMATE_ED25519_FINGERPRINT=$ED_FP
EOF
echo "==============================================================="
echo

# Non-interactive runs (CI, `bash tools/setup_relay.sh < /dev/null`) used to
# hang on this prompt, so only ask when there really is a terminal.
ans="${RELAY_YES:-}"
if [[ -z "$ans" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Append them to .env now? [y/N] " ans
  else
    ans=y
  fi
fi
if [[ "${ans:-n}" =~ ^[Yy]$ ]]; then
  [[ -f .env ]] || cp .env.example .env
  sed -i '/^PUBLIC_HOST=/d;/^TMATE_SERVER_HOST=/d;/^TMATE_PORTS=/d;/^TMATE_RSA_FINGERPRINT=/d;/^TMATE_ED25519_FINGERPRINT=/d' .env
  {
    echo "PUBLIC_HOST=$RELAY_HOST"
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
