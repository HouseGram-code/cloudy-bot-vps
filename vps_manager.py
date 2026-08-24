"""Docker-backed VPS manager for Cloudy VPS Bot.

Each "VPS" is a long-running Ubuntu 22.04 container with resource limits.
SSH access is provided through tmate, so no port forwarding is required.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import time
import uuid

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from config import (
    CONTAINER_PREFIX,
    MAX_VPS_PER_USER,
    PLAN,
    STATE_FILE,
    TMATE_ED25519_FINGERPRINT,
    TMATE_PORTS,
    TMATE_RSA_FINGERPRINT,
    TMATE_SERVER_HOST,
    TMATE_TIMEOUT,
    VPS_DNS,
    VPS_IMAGE,
    is_owner,
)

log = logging.getLogger("cloudy.vps")

IMAGE_CONTEXT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "images", "ubuntu-22.04"
)

TMATE_SOCK = "/tmp/cloudy.tmate.sock"
TMATE_LOG = "/tmp/cloudy.tmate.log"
TMATE_CONF = "/root/.tmate.conf"

# Static tmate build used when the distro package is unavailable.
_GH = "https://" + "github.com/tmate-io/tmate/releases/download"


class VPSError(Exception):
    """User-facing VPS error."""


class VPSManager:
    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as exc:  # pragma: no cover
            raise VPSError(
                "Cannot reach the Docker daemon. Make sure `/var/run/docker.sock` "
                "is mounted into the bot container."
            ) from exc
        self._lock = asyncio.Lock()
        self._state: dict = {"servers": {}}
        self._load_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                self._state = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            self._state = {"servers": {}}

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        tmp = f"{STATE_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._state, fh, indent=2)
        os.replace(tmp, STATE_FILE)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def get_record(self, user_id: int) -> dict | None:
        return self._state["servers"].get(str(user_id))

    def _container(self, user_id: int):
        record = self.get_record(user_id)
        if not record:
            return None
        try:
            return self.client.containers.get(record["container_id"])
        except NotFound:
            self._state["servers"].pop(str(user_id), None)
            self._save_state()
            return None

    async def has_vps(self, user_id: int) -> bool:
        return await asyncio.to_thread(lambda: self._container(user_id) is not None)

    def all_records(self) -> list[dict]:
        return list(self._state["servers"].values())

    # ------------------------------------------------------------------
    # Image build
    # ------------------------------------------------------------------
    def _ensure_image_sync(self) -> None:
        try:
            self.client.images.get(VPS_IMAGE)
            return
        except ImageNotFound:
            pass
        log.info("Building VPS image %s from %s", VPS_IMAGE, IMAGE_CONTEXT)
        self.client.images.build(path=IMAGE_CONTEXT, tag=VPS_IMAGE, rm=True, pull=True)

    async def ensure_image(self) -> None:
        await asyncio.to_thread(self._ensure_image_sync)

    # ------------------------------------------------------------------
    # Create / control
    # ------------------------------------------------------------------
    def _create_sync(self, user_id: int, username: str) -> dict:
        if (
            MAX_VPS_PER_USER
            and not is_owner(user_id)
            and self._container(user_id) is not None
        ):
            raise VPSError("You already own a VPS. Use `!manage` to control it.")

        self._ensure_image_sync()

        name = f"{CONTAINER_PREFIX}-{user_id}-{uuid.uuid4().hex[:6]}"
        mem_limit = f"{PLAN['ram_mb']}m"
        memswap = f"{PLAN['ram_mb'] + PLAN['swap_mb']}m"

        kwargs = dict(
            image=VPS_IMAGE,
            name=name,
            hostname=f"cloudy-{user_id % 100000}",
            detach=True,
            tty=True,
            stdin_open=True,
            mem_limit=mem_limit,
            memswap_limit=memswap,
            nano_cpus=int(PLAN["cpu_cores"] * 1_000_000_000),
            pids_limit=512,
            restart_policy={"Name": "unless-stopped"},
            # tmate needs a working resolver for ssh.tmate.io.
            dns=list(VPS_DNS) or None,
            security_opt=["no-new-privileges:true"],
            labels={
                "cloudy.vps": "true",
                "cloudy.owner": str(user_id),
                "cloudy.owner_name": username,
                "cloudy.os": PLAN["os_short"],
            },
            storage_opt={"size": f"{PLAN['disk_gb']}G"},
        )

        try:
            container = self.client.containers.run(**kwargs)
        except APIError:
            # storage_opt only works on some storage drivers (overlay2 + xfs).
            kwargs.pop("storage_opt", None)
            container = self.client.containers.run(**kwargs)

        record = {
            "container_id": container.id,
            "name": name,
            "owner_id": user_id,
            "owner_name": username,
            "os": PLAN["os"],
            "ram_mb": PLAN["ram_mb"],
            "cpu_cores": PLAN["cpu_cores"],
            "disk_gb": PLAN["disk_gb"],
            "bandwidth": PLAN["bandwidth"],
            "created_ts": time.time(),
            "ssh": None,
        }
        self._state["servers"][str(user_id)] = record
        self._save_state()
        return record

    async def create_vps(self, user_id: int, username: str) -> dict:
        async with self._lock:
            return await asyncio.to_thread(self._create_sync, user_id, username)

    def _action_sync(self, user_id: int, action: str) -> None:
        container = self._container(user_id)
        if container is None:
            raise VPSError("You do not have a VPS yet. Use `!deploy` to create one.")
        container.reload()
        if action == "start":
            if container.status == "running":
                raise VPSError("Your VPS is already running.")
            container.start()
        elif action == "stop":
            if container.status != "running":
                raise VPSError("Your VPS is already stopped.")
            container.stop(timeout=10)
        elif action == "restart":
            container.restart(timeout=10)
        else:
            raise VPSError(f"Unknown action: {action}")

        # Any power action invalidates the previous tmate session.
        record = self.get_record(user_id)
        if record:
            record["ssh"] = None
            self._save_state()

    async def power_action(self, user_id: int, action: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._action_sync, user_id, action)

    def _delete_sync(self, user_id: int) -> None:
        container = self._container(user_id)
        if container is not None:
            container.remove(force=True)
        self._state["servers"].pop(str(user_id), None)
        self._save_state()

    async def delete_vps(self, user_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._delete_sync, user_id)

    async def stop_if_running(self, user_id: int) -> bool:
        """Used by moderation: silently stop a user's server. Returns True if stopped."""

        def _work() -> bool:
            container = self._container(user_id)
            if container is None:
                return False
            container.reload()
            if container.status != "running":
                return False
            container.stop(timeout=10)
            record = self.get_record(user_id)
            if record:
                record["ssh"] = None
                self._save_state()
            return True

        async with self._lock:
            return await asyncio.to_thread(_work)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def _info_sync(self, user_id: int) -> dict:
        container = self._container(user_id)
        record = self.get_record(user_id)
        if container is None or record is None:
            raise VPSError("You do not have a VPS yet. Use `!deploy` to create one.")

        container.reload()
        attrs = container.attrs
        status = container.status

        info = {
            "id": container.id,
            "short_id": container.id[:12],
            "name": record["name"],
            "status": status,
            "os": record["os"],
            "ram_limit_mb": record["ram_mb"],
            "cpu_limit": record["cpu_cores"],
            "disk_gb": record["disk_gb"],
            "bandwidth": record["bandwidth"],
            "created_ts": record["created_ts"],
            "owner_id": record.get("owner_id", user_id),
            "ram_used_mb": 0,
            "cpu_percent": 0.0,
            "net_rx_mb": 0.0,
            "net_tx_mb": 0.0,
            "uptime_seconds": 0,
            "has_ssh": bool(record.get("ssh")),
        }

        if status == "running":
            started = attrs["State"].get("StartedAt", "")
            try:
                started_dt = dt.datetime.fromisoformat(started.split(".")[0].rstrip("Z"))
                started_dt = started_dt.replace(tzinfo=dt.timezone.utc)
                info["uptime_seconds"] = (
                    dt.datetime.now(dt.timezone.utc) - started_dt
                ).total_seconds()
            except ValueError:
                info["uptime_seconds"] = 0

            try:
                stats = container.stats(stream=False)
                mem = stats.get("memory_stats", {})
                usage = mem.get("usage", 0) - mem.get("stats", {}).get("cache", 0)
                info["ram_used_mb"] = max(0, round(usage / (1024 * 1024)))

                cpu = stats.get("cpu_stats", {})
                pre = stats.get("precpu_stats", {})
                cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get(
                    "cpu_usage", {}
                ).get("total_usage", 0)
                sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
                online = cpu.get("online_cpus") or 1
                if sys_delta > 0 and cpu_delta > 0:
                    percent = (cpu_delta / sys_delta) * online * 100.0
                    info["cpu_percent"] = min(
                        100.0, percent / max(0.1, float(record["cpu_cores"]))
                    )

                nets = stats.get("networks") or {}
                rx = sum(n.get("rx_bytes", 0) for n in nets.values())
                tx = sum(n.get("tx_bytes", 0) for n in nets.values())
                info["net_rx_mb"] = rx / (1024 * 1024)
                info["net_tx_mb"] = tx / (1024 * 1024)
            except Exception as exc:  # stats can fail transiently
                log.warning("stats failed for %s: %s", container.short_id, exc)

        return info

    async def get_info(self, user_id: int) -> dict:
        return await asyncio.to_thread(self._info_sync, user_id)

    # ------------------------------------------------------------------
    # tmate SSH
    # ------------------------------------------------------------------
    @staticmethod
    def _exec(container, script: str) -> tuple[int, str, str]:
        """Run a bash snippet in the guest, returning (code, stdout, stderr)."""
        result = container.exec_run(
            ["/bin/bash", "-lc", script],
            demux=True,
            environment={"TERM": "xterm-256color", "DEBIAN_FRONTEND": "noninteractive"},
        )
        out, err = result.output if isinstance(result.output, tuple) else (result.output, b"")
        return (
            result.exit_code,
            (out or b"").decode("utf-8", "replace").strip(),
            (err or b"").decode("utf-8", "replace").strip(),
        )

    def _ensure_tmate_binary(self, container) -> None:
        code, _, _ = self._exec(container, "command -v tmate")
        if code == 0:
            return

        log.info("tmate missing in %s, installing at runtime", container.short_id)
        install = (
            "set -e; "
            "(apt-get update -qq && apt-get install -y -qq tmate) >/dev/null 2>&1 || true; "
            "command -v tmate >/dev/null 2>&1 && exit 0; "
            "arch=$(uname -m); "
            'case "$arch" in x86_64) t=amd64 ;; aarch64) t=arm64v8 ;; armv7l) t=arm32v7 ;; '
            '*) echo "unsupported arch $arch" >&2; exit 1 ;; esac; '
            f'v=2.4.0; url="{_GH}/$v/tmate-$v-static-linux-$t.tar.xz"; '
            '(command -v wget >/dev/null && wget -qO /tmp/tmate.tar.xz "$url") '
            '|| curl -fsSL -o /tmp/tmate.tar.xz "$url"; '
            "tar -xf /tmp/tmate.tar.xz -C /tmp; "
            'mv /tmp/tmate-$v-static-linux-$t/tmate /usr/local/bin/tmate; '
            "chmod +x /usr/local/bin/tmate; "
            "rm -rf /tmp/tmate.tar.xz /tmp/tmate-$v-static-linux-$t"
        )
        code, out, err = self._exec(container, install)
        if code != 0:
            raise VPSError(
                "**tmate is not installed inside the VPS and could not be downloaded.**\n"
                "Rebuild the guest image so tmate is baked in:\n"
                "```bash\ndocker build --no-cache -t cloudy-vps:ubuntu-22.04 "
                "./images/ubuntu-22.04\n```\n"
                f"Installer output:\n```\n{(err or out or 'no output')[-600:]}\n```"
            )

    def _network_diagnostics(self, container) -> str:
        port_checks = "; ".join(
            f"echo '--- tcp {p} ---'; "
            f"(timeout 6 bash -c '</dev/tcp/{TMATE_SERVER_HOST}/{p}' "
            "&& echo 'TCP OK' || echo 'TCP FAILED')"
            for p in TMATE_PORTS
        )
        checks = (
            f"echo '--- dns ---'; (getent hosts {TMATE_SERVER_HOST} || echo 'DNS FAILED'); "
            f"{port_checks}; "
            "echo '--- tmate version ---'; (tmate -V 2>&1 | head -1); "
            f"echo '--- log ---'; (tail -n 12 {TMATE_LOG} 2>/dev/null || echo 'no log')"
        )
        _, out, err = self._exec(container, checks)
        return (out or err or "no diagnostics").strip()

    # -- relay port handling -------------------------------------------
    def _reachable_ports(self, container) -> list[int]:
        """Return the tmate relay ports the guest can actually reach."""
        probe = "; ".join(
            f"(timeout 5 bash -c '</dev/tcp/{TMATE_SERVER_HOST}/{p}' "
            f"&& echo 'OPEN {p}') 2>/dev/null"
            for p in TMATE_PORTS
        )
        _, out, _ = self._exec(container, probe)
        open_ports = [
            int(line.split()[1])
            for line in out.splitlines()
            if line.strip().startswith("OPEN ")
        ]
        # Keep the configured priority order; if nothing looks open we still
        # try every port, because some firewalls only block the probe.
        ordered = [p for p in TMATE_PORTS if p in open_ports]
        return ordered or list(TMATE_PORTS)

    def _write_tmate_conf(self, container, port: int) -> None:
        """Point tmate at the relay host/port that we want to use."""
        lines = [
            f"set -g tmate-server-host {TMATE_SERVER_HOST}",
            f"set -g tmate-server-port {port}",
        ]
        if TMATE_RSA_FINGERPRINT:
            lines.append(f"set -g tmate-server-rsa-fingerprint {TMATE_RSA_FINGERPRINT}")
        if TMATE_ED25519_FINGERPRINT:
            lines.append(
                f"set -g tmate-server-ed25519-fingerprint {TMATE_ED25519_FINGERPRINT}"
            )
        body = "\\n".join(lines)
        self._exec(container, f"printf '{body}\\n' > {TMATE_CONF}")

    def _kill_session(self, container) -> None:
        """Stop a previous tmate server without killing our own shell.

        NOTE: `pkill -f 'tmate -S <sock>'` also matches the `bash -lc "..."`
        process that is running the script itself, so it used to SIGTERM its
        own shell before tmate was ever started (that is why no tmate log was
        produced). The `[t]mate` bracket trick keeps the pattern from matching
        the command line that contains it.
        """
        self._exec(
            container,
            f"tmate -S {TMATE_SOCK} kill-server >/dev/null 2>&1; "
            f"pkill -f '[t]mate -S {TMATE_SOCK}' >/dev/null 2>&1; "
            f"rm -f {TMATE_SOCK}; exit 0",
        )

    def _start_session(self, container, port: int, budget: float) -> tuple[str, str]:
        """Start a detached tmate session on `port`.

        Returns (ssh_line, log_tail). `ssh_line` is empty when it did not work.
        """
        self._write_tmate_conf(container, port)
        self._kill_session(container)

        port_log = f"/tmp/cloudy.tmate.{port}.log"
        start = (
            f"rm -f {port_log}; "
            "mkdir -p /root/.ssh && chmod 700 /root/.ssh; "
            "export TERM=xterm-256color; "
            f"setsid nohup tmate -f {TMATE_CONF} -S {TMATE_SOCK} -F new-session -d "
            f"'TERM=xterm-256color bash -l' </dev/null > {port_log} 2>&1 & "
            f"sleep 2; ln -sf {port_log} {TMATE_LOG}; echo started; exit 0"
        )
        self._exec(container, start)

        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            code, out, _ = self._exec(
                container,
                f"tmate -S {TMATE_SOCK} display -p '#{{tmate_ssh}}' 2>/dev/null",
            )
            candidate = next(
                (ln.strip() for ln in out.splitlines() if ln.strip().startswith("ssh ")),
                "",
            )
            if code == 0 and candidate and "@" in candidate:
                return candidate, ""
            # If tmate died (relay refused the handshake) there is no point in
            # waiting for the whole budget - report the log straight away.
            _, alive, _ = self._exec(
                container, f"pgrep -f '[t]mate -S {TMATE_SOCK}' >/dev/null && echo yes"
            )
            if alive.strip() != "yes":
                break
            time.sleep(2)

        _, tail, _ = self._exec(
            container, f"tail -n 8 {port_log} 2>/dev/null || echo 'no log'"
        )
        return "", (tail or "no log").strip()

    def _tmate_sync(self, user_id: int, force_new: bool = False) -> str:
        container = self._container(user_id)
        record = self.get_record(user_id)
        if container is None or record is None:
            raise VPSError("You do not have a VPS yet. Use `!deploy` to create one.")

        container.reload()
        if container.status != "running":
            raise VPSError("Start your VPS first — a stopped server cannot open SSH.")

        if record.get("ssh") and not force_new:
            # Re-use the session only if it is genuinely still alive.
            code, out, _ = self._exec(
                container,
                f"tmate -S {TMATE_SOCK} display -p '#{{tmate_ssh}}' 2>/dev/null",
            )
            if code == 0 and out.startswith("ssh "):
                if out != record["ssh"]:
                    record["ssh"] = out
                    self._save_state()
                return out

        self._ensure_tmate_binary(container)

        # The default relay port (2200) is blocked on a lot of hosts, so try
        # every configured port and keep the first one that produces a session.
        candidates = self._reachable_ports(container)
        budget = max(20.0, float(TMATE_TIMEOUT - 10))
        per_port = max(15.0, budget / max(1, len(candidates)))

        ssh_line = ""
        used_port = None
        failures: list[str] = []
        for port in candidates:
            log.info(
                "opening tmate session for %s via %s:%s",
                container.short_id,
                TMATE_SERVER_HOST,
                port,
            )
            ssh_line, tail = self._start_session(container, port, per_port)
            if ssh_line:
                used_port = port
                break
            failures.append(f"[port {port}]\n{tail}")

        if not ssh_line:
            diag = self._network_diagnostics(container)
            tried = ", ".join(str(p) for p in candidates)
            fail_log = "\n".join(failures)[-700:]
            raise VPSError(
                "**Could not open a tmate session.**\n"
                f"Tried `{TMATE_SERVER_HOST}` on TCP **{tried}** — none of them "
                "completed the tmate handshake.\n"
                "Most common causes:\n"
                "\u2022 the relay port (2200) is blocked outbound → "
                "`sudo ufw allow out 2200/tcp` "
                "(or `sudo iptables -A OUTPUT -p tcp --dport 2200 -j ACCEPT`)\n"
                "\u2022 only 22/443 are open, but those ports on `ssh.tmate.io` are "
                "not the tmate relay, so the handshake is refused → run your own "
                "relay on an allowed port with `bash tools/setup_relay.sh` and put "
                "the printed `TMATE_*` values in `.env`.\n"
                f"```\n{fail_log or 'no tmate output'}\n```\n"
                f"```\n{diag[-700:]}\n```"
            )

        record["ssh"] = ssh_line
        record["tmate_port"] = used_port
        self._save_state()
        return ssh_line

    async def get_ssh(self, user_id: int, force_new: bool = False) -> str:
        return await asyncio.wait_for(
            asyncio.to_thread(self._tmate_sync, user_id, force_new),
            timeout=TMATE_TIMEOUT + 30,
        )
