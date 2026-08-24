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
    TMATE_TIMEOUT,
    VPS_IMAGE,
)

log = logging.getLogger("cloudy.vps")

IMAGE_CONTEXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "ubuntu-22.04")


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
        if MAX_VPS_PER_USER and self._container(user_id) is not None:
            raise VPSError(
                "You already own a VPS. Use `!manage` to control it."
            )

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
            cap_drop=["ALL"],
            cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER", "KILL"],
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
            "ram_used_mb": 0,
            "cpu_percent": 0.0,
            "net_rx_mb": 0.0,
            "net_tx_mb": 0.0,
            "uptime_seconds": 0,
            "ssh": record.get("ssh"),
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
                    # Normalize against the container's own vCPU allocation.
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
    def _tmate_sync(self, user_id: int, force_new: bool = False) -> str:
        container = self._container(user_id)
        record = self.get_record(user_id)
        if container is None or record is None:
            raise VPSError("You do not have a VPS yet. Use `!deploy` to create one.")

        container.reload()
        if container.status != "running":
            raise VPSError("Start your VPS first — a stopped server cannot open SSH.")

        if record.get("ssh") and not force_new:
            return record["ssh"]

        sock = "/tmp/cloudy.tmate.sock"
        script = (
            f"pkill -f 'tmate -S {sock}' >/dev/null 2>&1; "
            f"rm -f {sock}; "
            "mkdir -p /root/.ssh && chmod 700 /root/.ssh; "
            f"tmate -S {sock} new-session -d 'TERM=xterm-256color bash -l' "
            "&& "
            f"tmate -S {sock} wait tmate-ready "
            "&& "
            f"tmate -S {sock} display -p '#{{tmate_ssh}}'"
        )

        exit_code, output = container.exec_run(
            ["/bin/bash", "-lc", script],
            demux=False,
            environment={"TERM": "xterm-256color"},
        )
        text = (output or b"").decode("utf-8", "replace").strip()
        ssh_line = next(
            (ln.strip() for ln in reversed(text.splitlines()) if ln.strip().startswith("ssh ")),
            None,
        )
        if exit_code != 0 or not ssh_line:
            raise VPSError(
                "Could not open a tmate session.\n"
                "```\n" + (text[-500:] or "no output") + "\n```\n"
                "The VPS needs outbound internet access to reach `tmate.io`."
            )

        record["ssh"] = ssh_line
        self._save_state()
        return ssh_line

    async def get_ssh(self, user_id: int, force_new: bool = False) -> str:
        return await asyncio.wait_for(
            asyncio.to_thread(self._tmate_sync, user_id, force_new),
            timeout=TMATE_TIMEOUT,
        )
