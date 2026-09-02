"""Self-hosted tmate relay for hosts with a filtered egress.

`ssh.tmate.io` runs the relay on TCP **2200 only**. Ports 22 and 443 on that
host do accept TCP, but they never send an SSH banner, so the tmate handshake
can never finish there. When the provider filters outbound 2200 - a datacenter
egress rule that `ufw allow out 2200/tcp` cannot undo, because outbound is
already allowed locally - there is simply no public relay left to reach.

The fix that always works is to run the relay on this machine:

* the relay container uses **host networking**, so it binds the host's own
  addresses directly;
* guest containers connect to that address, which never leaves the machine
  (no egress filter can touch it, no Docker NAT hairpin either);
* your users SSH to `PUBLIC_HOST:<relay port>`, which only needs an *inbound*
  port to be open - exactly the rule people actually can add.

The host keys live in a named Docker volume, so the fingerprints tmate clients
pin survive restarts and image upgrades. What we learn is cached in
`data/relay.json`, so the bot re-uses the relay after a restart with no `.env`
editing at all.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from config import (
    PUBLIC_HOST,
    RELAY_FILE,
    TMATE_RELAY_AUTOFIX,
    TMATE_RELAY_IMAGE,
    TMATE_RELAY_NAME,
    TMATE_RELAY_PORTS,
    TMATE_RELAY_VOLUME,
    VPS_IMAGE,
)

log = logging.getLogger("cloudy.relay")

KEYS_MOUNT = "/etc/tmate-ssh-server-keys"

_HOSTISH = re.compile(r"^[A-Za-z0-9._:-]{3,255}$")

# ssh-keygen ships with openssh-client. The guest image has bash + apt, so we
# borrow it from a throwaway container instead of requiring anything on the
# host (the bot itself usually runs in a slim Python image without it).
_KEYGEN = (
    "set -e; cd /keys; "
    "command -v ssh-keygen >/dev/null 2>&1 || "
    "{ apt-get update -qq >/dev/null 2>&1; "
    "apt-get install -y -qq openssh-client >/dev/null 2>&1; }; "
    "command -v ssh-keygen >/dev/null 2>&1 || { echo NOKEYGEN >&2; exit 3; }; "
    "[ -f ssh_host_rsa_key ] || ssh-keygen -q -t rsa -b 2048 -N '' -f ssh_host_rsa_key; "
    "[ -f ssh_host_ed25519_key ] || ssh-keygen -q -t ed25519 -N '' -f ssh_host_ed25519_key; "
    "chmod 600 ssh_host_rsa_key ssh_host_ed25519_key; "
    "echo RSA=$(ssh-keygen -l -E sha256 -f ssh_host_rsa_key.pub | awk '{print $2}'); "
    "echo ED=$(ssh-keygen -l -E sha256 -f ssh_host_ed25519_key.pub | awk '{print $2}')"
)


def probe_script(host: str, port: int) -> str:
    """Bash snippet that proves an SSH relay really answers on host:port.

    A plain TCP connect is not proof (that is exactly how `ssh.tmate.io:443`
    fools people), and a read-only probe is not proof either:
    tmate-ssh-server waits for the CLIENT identification string before it says
    anything, so we must send our own version line first, then read.
    """
    return (
        "b=$(timeout 8 bash -c '"
        f"exec 3<>/dev/tcp/{host}/{port} || exit 1; "
        'printf "SSH-2.0-cloudy_probe\\r\\n" >&3; '
        "head -c 60 <&3' 2>/dev/null); "
        'case "$b" in SSH-*) echo RELAY ;; *) echo NO ;; esac'
    )


def gateway_script() -> str:
    """Print the host's address as seen from inside a container.

    A container cannot reach the machine's *public* IP on most providers: with
    1:1 NAT that address is not on any local interface, so the packet leaves
    the box and never comes back. The default gateway of the container is the
    Docker bridge, i.e. this very host - and the relay (host networking)
    listens there too.
    """
    return (
        "ip route 2>/dev/null | awk '/^default/{print $3; exit}' || "
        "route -n 2>/dev/null | awk '/^0.0.0.0/{print $2; exit}' || true"
    )


class RelayError(Exception):
    """The local relay could not be prepared."""


class TmateRelay:
    """Lifecycle of the `cloudy-tmate-relay` container."""

    def __init__(self) -> None:
        self._client = None
        self._cache: dict | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # docker plumbing
    # ------------------------------------------------------------------
    def _docker(self):
        if self._client is None:
            try:
                client = docker.from_env()
                client.ping()
            except DockerException as exc:
                raise RelayError(f"Docker is not reachable: {exc}") from exc
            self._client = client
        return self._client

    def _run(
        self,
        script: str,
        *,
        network: str = "",
        keys: bool = False,
        privileged: bool = False,
    ) -> str:
        """Run a short helper script in a throwaway guest-image container."""
        kwargs: dict = {
            "image": VPS_IMAGE,
            "command": ["/bin/bash", "-lc", script],
            "remove": True,
            "stdout": True,
            "stderr": True,
        }
        if network:
            kwargs["network_mode"] = network
        if privileged:
            # Only for the single iptables ACCEPT rule in open_firewall().
            kwargs["privileged"] = True
            kwargs["cap_add"] = ["NET_ADMIN"]
        if keys:
            kwargs["volumes"] = {TMATE_RELAY_VOLUME: {"bind": "/keys", "mode": "rw"}}
        try:
            out = self._docker().containers.run(**kwargs)
        except Exception as exc:  # ContainerError / APIError / anything
            out = getattr(exc, "stderr", None) or str(exc)
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return (out or "").strip()

    @staticmethod
    def _said_relay(output: str) -> bool:
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        return bool(lines) and lines[-1] == "RELAY"

    # ------------------------------------------------------------------
    # persisted state
    # ------------------------------------------------------------------
    def state(self) -> dict:
        if self._cache is not None:
            return dict(self._cache)
        data: dict = {}
        try:
            with open(RELAY_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
        self._cache = data
        return dict(data)

    def _save(self, data: dict) -> None:
        self._cache = dict(data)
        try:
            os.makedirs(os.path.dirname(RELAY_FILE) or ".", exist_ok=True)
            tmp = f"{RELAY_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
            os.replace(tmp, RELAY_FILE)
        except OSError as exc:
            # A read-only data dir must never break SSH: keep it in memory.
            log.warning("could not save %s: %s", RELAY_FILE, exc)

    # ------------------------------------------------------------------
    # container state
    # ------------------------------------------------------------------
    def container(self):
        try:
            return self._docker().containers.get(TMATE_RELAY_NAME)
        except (NotFound, DockerException, RelayError):
            return None

    def running(self) -> bool:
        container = self.container()
        if container is None:
            return False
        try:
            container.reload()
        except DockerException:
            return False
        return container.status == "running"

    def logs(self) -> str:
        container = self.container()
        if container is None:
            return ""
        try:
            return container.logs(tail=20).decode("utf-8", "replace").strip()
        except (DockerException, AttributeError):
            return ""

    def settings(self) -> dict:
        """Relay to point guests at, or `{}` when we have no usable one."""
        state = self.state()
        if not state.get("host") or not state.get("port"):
            return {}
        if not self.running():
            return {}
        return state

    def status(self) -> dict:
        state = self.state()
        return {
            "configured": bool(state.get("host") and state.get("port")),
            "running": self.running(),
            "host": str(state.get("host") or PUBLIC_HOST or ""),
            "port": int(state.get("port") or TMATE_RELAY_PORTS[0]),
            "rsa": str(state.get("rsa") or ""),
            "ed25519": str(state.get("ed25519") or ""),
            "guest_host": str(state.get("guest_host") or ""),
            "guest_ok": bool(state.get("guest_ok")),
            "updated": float(state.get("updated") or 0.0),
            "image": TMATE_RELAY_IMAGE,
            "name": TMATE_RELAY_NAME,
        }

    # ------------------------------------------------------------------
    # public address
    # ------------------------------------------------------------------
    def detect_host(self) -> str:
        """Address guests (and users) should SSH to.

        `PUBLIC_HOST` wins, then whatever worked last time, and only then an
        "echo my IP" service - that one reports the NAT gateway the traffic
        exits through, which is not always this machine, so it is a hint that
        gets verified afterwards, never a truth.
        """
        if PUBLIC_HOST:
            return PUBLIC_HOST
        state = self.state()
        if state.get("host"):
            return str(state["host"])
        out = self._run(
            "curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || "
            "curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true"
        )
        candidate = out.splitlines()[-1].strip() if out.splitlines() else ""
        return candidate if _HOSTISH.match(candidate) else ""

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def ensure(self, host: str = "", port: int = 0, force: bool = False) -> dict:
        """Make sure a working local relay exists; returns `status()`."""
        with self._lock:
            return self._ensure(host.strip(), int(port or 0), force)

    def _ensure(self, host: str, port: int, force: bool) -> dict:
        host = host or self.detect_host()
        if not host:
            raise RelayError(
                "I do not know which address your users should SSH to. "
                "Run `!relay <public-ip-or-domain>` once, or set `PUBLIC_HOST` "
                "in `.env`."
            )
        if not _HOSTISH.match(host):
            raise RelayError(f"`{host[:60]}` does not look like an IP or a domain.")

        state = self.state()
        if (
            not force
            and self.running()
            and str(state.get("host")) == host
            and (not port or int(state.get("port") or 0) == port)
            and state.get("rsa")
            and state.get("ed25519")
            # Without a known guest path the relay is useless, so rebuild.
            and state.get("guest_host")
        ):
            return self.status()

        client = self._docker()

        # 1. host keys in a named volume (stable fingerprints)
        try:
            client.volumes.get(TMATE_RELAY_VOLUME)
        except (NotFound, DockerException):
            try:
                client.volumes.create(TMATE_RELAY_VOLUME)
            except DockerException as exc:
                raise RelayError(f"could not create the key volume: {exc}") from exc

        out = self._run(_KEYGEN, keys=True)
        rsa = ed25519 = ""
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("RSA="):
                rsa = line[4:].strip()
            elif line.startswith("ED="):
                ed25519 = line[3:].strip()
        if not rsa.startswith("SHA256:") or not ed25519.startswith("SHA256:"):
            raise RelayError(
                "could not generate the relay host keys:\n"
                f"```\n{out[-500:] or 'no output'}\n```"
            )

        # 2. relay image
        try:
            client.images.get(TMATE_RELAY_IMAGE)
        except (ImageNotFound, DockerException):
            log.info("pulling %s", TMATE_RELAY_IMAGE)
            try:
                client.images.pull(TMATE_RELAY_IMAGE)
            except DockerException as exc:
                raise RelayError(
                    f"could not pull `{TMATE_RELAY_IMAGE}`: {exc}"
                ) from exc

        # 3. first port that really serves SSH wins
        ports = [port] if port else list(TMATE_RELAY_PORTS)
        errors: list[str] = []
        for candidate in ports:
            self._remove()
            try:
                client.containers.run(
                    TMATE_RELAY_IMAGE,
                    name=TMATE_RELAY_NAME,
                    detach=True,
                    # Host networking on purpose: no published ports, no NAT
                    # hairpin, and the guests reach it on the host's own IP.
                    network_mode="host",
                    cap_add=["SYS_ADMIN"],
                    restart_policy={"Name": "unless-stopped"},
                    volumes={
                        TMATE_RELAY_VOLUME: {"bind": KEYS_MOUNT, "mode": "rw"}
                    },
                    environment={
                        # This image is driven by env vars, not CLI flags.
                        "SSH_KEYS_PATH": KEYS_MOUNT,
                        "SSH_HOSTNAME": host,
                        "SSH_PORT_LISTEN": str(candidate),
                        "SSH_PORT": str(candidate),
                    },
                )
            except DockerException as exc:
                errors.append(f"port {candidate}: {exc}")
                continue

            if not self._wait_ready(candidate):
                errors.append(
                    f"port {candidate}: no SSH banner\n{self.logs()[-300:]}"
                )
                continue

            # What matters is the path the GUESTS take, and it is usually not
            # the public IP: behind provider NAT that address is not local, so
            # a container dialling it sends the packet out of the machine and
            # never gets an answer. The relay listens on every host address,
            # so the bridge gateway is the one that works.
            guest_host = self.find_guest_host(candidate, host)
            if not guest_host:
                if "OPENED" in self.open_firewall(candidate):
                    guest_host = self.find_guest_host(candidate, host)

            data = {
                "host": host,
                "port": int(candidate),
                "rsa": rsa,
                "ed25519": ed25519,
                "guest_host": guest_host,
                "guest_ok": bool(guest_host),
                "updated": time.time(),
            }
            self._save(data)
            log.info(
                "self-hosted tmate relay ready on %s:%s (guests via %s)",
                host,
                candidate,
                guest_host or "?",
            )
            return self.status()

        self._remove()
        tried = ", ".join(str(p) for p in ports)
        raise RelayError(
            f"the relay never answered on TCP {tried}:\n"
            f"```\n{chr(10).join(errors)[-600:] or 'no output'}\n```"
        )

    # ------------------------------------------------------------------
    # the address the guests must dial
    # ------------------------------------------------------------------
    def guest_candidates(self, host: str = "") -> list[str]:
        """Addresses of THIS host that a guest container can really dial."""
        found: list[str] = []

        def add(value: str) -> None:
            value = (value or "").strip()
            if value and value not in found and _HOSTISH.match(value):
                found.append(value)

        state = self.state()
        add(str(state.get("guest_host") or ""))

        # The gateway a throwaway container sees IS the Docker bridge.
        gateway = self._run(gateway_script()).splitlines()
        add(gateway[-1] if gateway else "")

        # ...and the gateway of every other bridge network, in case the guests
        # do not sit on the default one.
        try:
            for net in self._docker().networks.list(filters={"driver": "bridge"}):
                for cfg in (net.attrs.get("IPAM") or {}).get("Config") or []:
                    add(str(cfg.get("Gateway") or ""))
        except Exception:  # pragma: no cover - docker quirks
            pass

        add("172.17.0.1")

        # Private addresses of the host itself (host networking again).
        for value in self._run("hostname -I 2>/dev/null || true", network="host").split():
            add(value)

        add(host)
        return found

    def find_guest_host(self, port: int, host: str = "") -> str:
        """First address of this host that answers as a relay from a guest."""
        for candidate in self.guest_candidates(
            host or str(self.state().get("host") or "")
        ):
            if self._said_relay(self._run(probe_script(candidate, port))):
                return candidate
        return ""

    def remember_guest_host(self, guest_host: str) -> None:
        """Persist the address that actually worked from inside a VPS."""
        state = self.state()
        if not state.get("host") or state.get("guest_host") == guest_host:
            return
        state["guest_host"] = guest_host
        state["guest_ok"] = True
        state["updated"] = time.time()
        self._save(state)

    def open_firewall(self, port: int) -> str:
        """Best effort: let container traffic reach the relay port.

        With ufw's default `deny (incoming)` the packets a guest sends to the
        bridge gateway hit the host INPUT chain and are dropped, so the relay
        looks dead from inside a VPS while `127.0.0.1` works fine. One
        idempotent ACCEPT rule fixes that and touches nothing else.
        """
        if not TMATE_RELAY_AUTOFIX:
            return "disabled"
        script = (
            "command -v iptables >/dev/null 2>&1 || "
            "{ apt-get update -qq >/dev/null 2>&1; "
            "apt-get install -y -qq iptables >/dev/null 2>&1; }; "
            "command -v iptables >/dev/null 2>&1 || { echo NOIPTABLES; exit 0; }; "
            "for c in INPUT DOCKER-USER; do "
            f"iptables -C $c -p tcp --dport {port} -j ACCEPT 2>/dev/null || "
            f"iptables -I $c -p tcp --dport {port} -j ACCEPT 2>/dev/null || true; "
            "done; echo OPENED"
        )
        out = self._run(script, network="host", privileged=True)
        log.info("relay firewall fix for port %s: %s", port, out[-120:] or "no output")
        return out

    def _wait_ready(self, port: int, tries: int = 12) -> bool:
        """A "running" container is not enough - a crash loop looks the same."""
        for _ in range(tries):
            time.sleep(2)
            if not self.running():
                continue
            if self._said_relay(self._run(probe_script("127.0.0.1", port), network="host")):
                return True
        return False

    def _remove(self) -> None:
        container = self.container()
        if container is None:
            return
        try:
            container.remove(force=True)
        except DockerException:
            pass
        time.sleep(1)

    def stop(self) -> bool:
        """Remove the relay and go back to the public tmate.io settings."""
        with self._lock:
            existed = self.container() is not None
            self._remove()
            self._save({})
            return existed


RELAY = TmateRelay()
