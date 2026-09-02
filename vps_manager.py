"""Docker-backed VPS manager for Cloudy VPS Bot.

Each "VPS" is a long-running Ubuntu 22.04 container with resource limits.
Access is provided through the sshx browser terminal, so no ports are opened.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import base64
import json
import logging
import os
import re
import tempfile
import time
import uuid

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from i18n import t
from plan_store import PLAN_STORE
from slots import SLOTS
from config import (
    COMMAND_PREFIX,
    CONTAINER_PREFIX,
    MAX_VPS_PER_USER,
    PLAN,
    SSHX_BINARY_BASE,
    SSHX_ENABLED,
    SSHX_INSTALL_URL,
    SSHX_SERVER,
    SSHX_TIMEOUT,
    STATE_FILE,
    VPS_DNS,
    VPS_IMAGE,
    VPS_LIFETIME_DAYS,
    VPS_LIFETIME_SECONDS,
    is_owner,
)

log = logging.getLogger("cloudy.vps")

IMAGE_CONTEXT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "images", "ubuntu-22.04"
)

BANNER_SCRIPT = os.path.join(IMAGE_CONTEXT, "cloudy-banner.sh")
BANNER_PATH = "/usr/local/bin/cloudy-banner"
LOGIN_PATH = "/usr/local/bin/cloudy-login"
PROFILE_HOOK = "/etc/profile.d/00-cloudy-banner.sh"

# Shell snippet sourced by every interactive shell in the guest.
BANNER_HOOK = """# cloudy-banner (managed by Cloudy VPS Bot)
export CLOUDY_LANG="${CLOUDY_LANG:-%(lang)s}"
export CLOUDY_RAM_MB="${CLOUDY_RAM_MB:-%(ram)s}"
export CLOUDY_DISK_GB="${CLOUDY_DISK_GB:-%(disk)s}"
export CLOUDY_CPU="${CLOUDY_CPU:-%(cpu)s}"
alias banner='/usr/local/bin/cloudy-banner'
case $- in
  *i*)
    if [ -z "$CLOUDY_BANNER_SHOWN" ] && [ -x /usr/local/bin/cloudy-banner ]; then
      export CLOUDY_BANNER_SHOWN=1
      /usr/local/bin/cloudy-banner
    fi
    ;;
esac
"""

# guest image has a stripped down /root/.profile.
LOGIN_WRAPPER = """#!/bin/bash
export TERM="${TERM:-xterm-256color}"
export CLOUDY_LANG="${CLOUDY_LANG:-%(lang)s}"
export CLOUDY_RAM_MB="${CLOUDY_RAM_MB:-%(ram)s}"
export CLOUDY_DISK_GB="${CLOUDY_DISK_GB:-%(disk)s}"
export CLOUDY_CPU="${CLOUDY_CPU:-%(cpu)s}"
if [ -x /usr/local/bin/cloudy-banner ]; then
  /usr/local/bin/cloudy-banner
fi
export CLOUDY_BANNER_SHOWN=1
exec bash -l
"""

# sshx: browser terminal. The client is a single static binary; it prints one
# line like "https://sshx.io/s/wC8cc6Mbjv#W0apHWrt8OaX4W" and keeps running.
SSHX_BIN = "/usr/local/bin/sshx"
SSHX_LOG = "/tmp/cloudy.sshx.log"
SSHX_URL_RE = re.compile(r"https?://[^\s\"']+/s/[A-Za-z0-9_-]+#[A-Za-z0-9_-]+")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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
        # Global slot limit (e.g. 5/5) shared with the bot and the admin panel.
        self.slots = SLOTS
        self._load_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                self._state = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            self._state = {"servers": {}}
        if not isinstance(self._state, dict) or "servers" not in self._state:
            self._state = {"servers": {}}

    def _save_state(self) -> None:
        """Persist the state file without ever breaking the caller.

        The old version let OSError bubble up: on a host install
        `os.makedirs("/app/data")` raised `[Errno 13] Permission denied:
        '/app'` in the middle of `!deploy`, so the container was created but
        the deployment was reported as failed. The data folder is resolved to
        a writable one now (config.DATA_DIR) and any leftover I/O problem is
        logged - plus a /tmp copy - instead of killing the command.
        """
        try:
            os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
            tmp = f"{STATE_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, STATE_FILE)
            return
        except OSError as exc:
            log.error("could not save state to %s: %s", STATE_FILE, exc)

        fallback = os.path.join(tempfile.gettempdir(), "cloudy-vps_state.json")
        try:
            with open(fallback, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            log.warning("state written to %s instead", fallback)
        except OSError as exc:  # pragma: no cover
            log.error("state could not be persisted at all: %s", exc)

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
    # Global capacity (slots)
    # ------------------------------------------------------------------
    def _all_vps_containers(self) -> list:
        """Every guest container created by the bot (running or stopped)."""
        try:
            return self.client.containers.list(
                all=True, filters={"label": "cloudy.vps=true"}
            )
        except APIError as exc:  # pragma: no cover
            log.warning("could not list VPS containers: %s", exc)
            return []

    def _stats_sync(self) -> dict:
        """Live counters for the admin panel: running / stopped / slots."""
        running = stopped = 0
        for container in self._all_vps_containers():
            try:
                status = container.status
            except Exception:  # pragma: no cover
                status = ""
            if status == "running":
                running += 1
            else:
                stopped += 1
        used = running + stopped
        total = self.slots.total if self.slots is not None else used
        return {
            "running": running,
            "stopped": stopped,
            "used": used,
            "slots": int(total),
            "free": max(0, int(total) - used),
            "full": used >= int(total),
        }

    async def stats(self) -> dict:
        return await asyncio.to_thread(self._stats_sync)

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
    def _owned_containers(self, user_id: int) -> list:
        """Every container (running or stopped) that belongs to this user."""
        try:
            return self.client.containers.list(
                all=True, filters={"label": f"cloudy.owner={user_id}"}
            )
        except APIError as exc:  # pragma: no cover
            log.warning("could not list containers for %s: %s", user_id, exc)
            record_container = self._container(user_id)
            return [record_container] if record_container else []

    def _records_for(self, user_id: int) -> list[tuple[str, dict]]:
        return [
            (key, rec)
            for key, rec in self._state["servers"].items()
            if int(rec.get("owner_id", -1)) == int(user_id)
        ]

    def capacity(self) -> tuple[int, int]:
        """Return (used, slots) for the whole host."""
        used = len(self._all_vps_containers())
        total = self.slots.total if self.slots is not None else used
        return used, int(total)

    def quota(self, user_id: int) -> tuple[int, int | None]:
        """Return (used, limit). `limit` is None for staff = unlimited."""
        used = len(self._owned_containers(user_id))
        if is_owner(user_id) or not MAX_VPS_PER_USER:
            return used, None
        return used, int(MAX_VPS_PER_USER)

    _LOGIN_CLEAN = re.compile(r"[^a-z0-9_-]+")

    @classmethod
    def normalize_login(cls, value: str, fallback: str = "root") -> str:
        """Turn free-form staff input into a valid Linux login."""
        login = cls._LOGIN_CLEAN.sub("", str(value or "").strip().lower())
        login = login.lstrip("-_")[:32]
        if not login or login[0].isdigit():
            return fallback
        return login

    # Accounts that already exist in the guest image: taking one over would
    # break the container instead of handing out a login.
    _LOGIN_RESERVED = {
        "bin",
        "daemon",
        "games",
        "lp",
        "mail",
        "man",
        "news",
        "nobody",
        "proxy",
        "root",
        "sshd",
        "sync",
        "sys",
        "systemd",
        "ubuntu",
        "uucp",
        "www-data",
    }

    @classmethod
    def suggest_login(cls, *hints: str) -> str:
        """Derive a valid Linux login from a Discord account name.

        Used when `!givevps` is called without a username: staff should not
        have to invent one, and a Discord name may contain spaces, dots,
        emoji or Cyrillic - none of which `useradd` accepts. The first hint
        that survives the cleanup wins.
        """
        for hint in hints:
            raw = str(hint or "").strip().lower().split("#")[0]
            raw = raw.replace(" ", "-").replace(".", "-")
            login = cls._LOGIN_CLEAN.sub("", raw).strip("-_")[:32]
            if not login:
                continue
            if login[0].isdigit():
                # Linux logins cannot start with a digit.
                login = f"u{login}"[:32]
            if login in cls._LOGIN_RESERVED:
                login = f"{login}-vps"[:32]
            return login
        return "root"

    def _create_sync(
        self,
        user_id: int,
        username: str,
        lang: str = "en",
        overrides: dict | None = None,
    ) -> dict:
        # `overrides` is the staff grant path (!givevps): custom login, RAM,
        # disk and term - and no quota / slot checks, because staff decides.
        opts = dict(overrides or {})
        forced = bool(opts.get("force"))
        # Hard quota: regular users get MAX_VPS_PER_USER (1), staff unlimited.
        # Counting real containers instead of state entries keeps the limit
        # working even if the state file was lost or edited by hand.
        # Global capacity: when every slot is taken nobody but staff can
        # deploy a new VPS until one is deleted or the limit is raised.
        if self.slots is not None and not forced and not is_owner(user_id):
            used_total, total = self.capacity()
            if used_total >= total:
                raise VPSError(
                    f"**{t(lang, 'slots.full_title')}** \u2014 `{used_total}/{total}`\n"
                    + t(lang, "slots.full", total=total, prefix=COMMAND_PREFIX)
                )

        if MAX_VPS_PER_USER and not forced and not is_owner(user_id):
            used = len(self._owned_containers(user_id))
            if used >= int(MAX_VPS_PER_USER):
                # Localized (the old message was English-only and hardcoded
                # the "!" prefix).
                raise VPSError(
                    f"**{t(lang, 'vps.limit_title')}**\n"
                    + t(
                        lang,
                        "vps.limit",
                        limit=int(MAX_VPS_PER_USER),
                        used=used,
                        prefix=COMMAND_PREFIX,
                    )
                )

        self._ensure_image_sync()

        name = f"{CONTAINER_PREFIX}-{user_id}-{uuid.uuid4().hex[:6]}"
        # Live plan: staff may have raised RAM / disk / vCPU since start-up.
        plan = dict(PLAN_STORE.plan())
        # Per-server overrides from !givevps win over the global plan.
        for _key in ("ram_mb", "swap_mb", "disk_gb"):
            if opts.get(_key) is not None:
                plan[_key] = max(0, int(opts[_key]))
        if opts.get("cpu_cores") is not None:
            plan["cpu_cores"] = max(0.1, float(opts["cpu_cores"]))
        plan["ram_mb"] = max(128, int(plan["ram_mb"]))
        plan["disk_gb"] = max(1, int(plan["disk_gb"]))
        plan["swap_mb"] = max(0, int(plan.get("swap_mb") or 0))
        login = self.normalize_login(opts.get("login") or "root")
        mem_limit = f"{plan['ram_mb']}m"
        memswap = f"{plan['ram_mb'] + plan['swap_mb']}m"

        kwargs = dict(
            image=VPS_IMAGE,
            name=name,
            hostname=f"cloudy-{user_id % 100000}",
            detach=True,
            tty=True,
            stdin_open=True,
            mem_limit=mem_limit,
            memswap_limit=memswap,
            nano_cpus=int(plan["cpu_cores"] * 1_000_000_000),
            pids_limit=512,
            restart_policy={"Name": "unless-stopped"},
            dns=list(VPS_DNS) or None,
            security_opt=["no-new-privileges:true"],
            # CLOUDY_LANG localizes the guest login banner (ru / en).
            environment={
                "TERM": "xterm-256color",
                "LANG": "C.UTF-8",
                "CLOUDY_LANG": "ru" if str(lang).startswith("ru") else "en",
                # The banner shows the plan limits, not the host metrics.
                "CLOUDY_RAM_MB": str(plan["ram_mb"]),
                "CLOUDY_DISK_GB": str(plan["disk_gb"]),
                "CLOUDY_CPU": str(plan["cpu_cores"]),
                "CLOUDY_USER": login,
            },
            labels={
                "cloudy.vps": "true",
                "cloudy.owner": str(user_id),
                "cloudy.owner_name": username,
                "cloudy.os": plan["os_short"],
            },
            storage_opt={"size": f"{plan['disk_gb']}G"},
        )

        try:
            container = self.client.containers.run(**kwargs)
        except APIError:
            # storage_opt only works on some storage drivers (overlay2 + xfs).
            kwargs.pop("storage_opt", None)
            container = self.client.containers.run(**kwargs)

        # Old images shipped a broken /etc/motd - refresh the banner on every
        # deployment so the guest always greets with the new one.
        try:
            self._install_banner(container, lang)
        except Exception as exc:  # pragma: no cover
            log.warning("could not install banner: %s", exc)

        # Staff can hand out a named login: !givevps <@user> <username> ...
        if login != "root":
            try:
                self._ensure_guest_user(container, login)
            except Exception as exc:  # pragma: no cover
                log.warning("could not create the guest login %s: %s", login, exc)
                login = "root"

        created_ts = time.time()
        # 1.3 Beta: `!deploy` grants the server for VPS_LIFETIME_DAYS days
        # (30 by default) and `!givevps` may pass its own number of days.
        # 0 disables the term completely.
        term_days = opts.get("days")
        term_days = int(VPS_LIFETIME_DAYS if term_days is None else term_days)
        expires_ts = created_ts + term_days * 86400.0 if term_days > 0 else 0.0
        record = {
            "container_id": container.id,
            "name": name,
            "hostname": kwargs.get("hostname") or name,
            "owner_id": user_id,
            "owner_name": username,
            # Login the terminal sessions land in (full root access).
            "ssh_user": "root",
            # Account created inside the guest for the owner (!givevps).
            "login": login,
            "os": plan["os"],
            "ram_mb": plan["ram_mb"],
            "swap_mb": plan.get("swap_mb", 0),
            "cpu_cores": plan["cpu_cores"],
            "disk_gb": plan["disk_gb"],
            "bandwidth": plan["bandwidth"],
            "created_ts": created_ts,
            "term_days": term_days,
            "expires_ts": expires_ts,
            "warned_days": [],
        }
        # Staff may own several servers: keep the newest one as the primary
        # record (the one !manage / !destroy work on) and park the previous
        # ones under a suffixed key so they stay visible in !servers.
        primary = self._state["servers"].get(str(user_id))
        if primary and primary.get("container_id") != container.id:
            parked = f"{user_id}:{primary['container_id'][:12]}"
            self._state["servers"][parked] = primary
        self._state["servers"][str(user_id)] = record
        self._save_state()
        return record

    async def create_vps(self, user_id: int, username: str, lang: str = "en") -> dict:
        async with self._lock:
            return await asyncio.to_thread(self._create_sync, user_id, username, lang)

    async def create_custom(
        self,
        user_id: int,
        username: str,
        *,
        login: str = "root",
        ram_mb: int | None = None,
        disk_gb: int | None = None,
        cpu_cores: float | None = None,
        swap_mb: int | None = None,
        days: int | None = None,
        lang: str = "en",
    ) -> dict:
        """Staff grant (`!givevps`): custom login / RAM / disk / term, no quota."""
        overrides = {
            "login": login,
            "ram_mb": ram_mb,
            "disk_gb": disk_gb,
            "cpu_cores": cpu_cores,
            "swap_mb": swap_mb,
            "days": days,
            "force": True,
        }
        async with self._lock:
            return await asyncio.to_thread(
                self._create_sync, user_id, username, lang, overrides
            )

    def _ensure_guest_user(self, container, login: str) -> None:
        """Create a sudo-enabled account inside the guest (idempotent)."""
        script = (
            f"id -u {login} >/dev/null 2>&1 || useradd -m -s /bin/bash {login}; "
            f"usermod -aG sudo {login} 2>/dev/null || true; "
            f"passwd -d {login} >/dev/null 2>&1 || true; "
            f"mkdir -p /home/{login} && chown -R {login}:{login} /home/{login}; "
            f"printf '%s\\n' '{login} ALL=(ALL) NOPASSWD:ALL' "
            f"> /etc/sudoers.d/90-cloudy-{login} 2>/dev/null || true; "
            f"chmod 0440 /etc/sudoers.d/90-cloudy-{login} 2>/dev/null || true; "
            f"id -u {login}"
        )
        code, out, err = self._exec(container, script)
        if code not in (0, None):
            raise VPSError(f"could not create the login `{login}`: {err or out}")

    # ------------------------------------------------------------------
    # Login banner (works on old containers too, no image rebuild needed)
    # ------------------------------------------------------------------
    @staticmethod
    def _guest_lang(container, fallback: str = "en") -> str:
        """Read CLOUDY_LANG from the container environment."""
        try:
            env = container.attrs.get("Config", {}).get("Env") or []
            for item in env:
                if item.startswith("CLOUDY_LANG="):
                    value = item.split("=", 1)[1]
                    return "ru" if value.startswith("ru") else "en"
        except Exception:  # pragma: no cover
            pass
        return "ru" if str(fallback).startswith("ru") else "en"

    @staticmethod
    def _guest_env(container) -> dict:
        """Environment of a guest container (its own CLOUDY_* limits)."""
        env = {}
        try:
            raw = container.attrs.get("Config", {}).get("Env") or []
        except Exception:  # pragma: no cover - container may be gone
            return env
        for item in raw:
            if "=" in str(item):
                key, _, value = str(item).partition("=")
                env[key] = value
        return env

    def _install_banner(self, container, lang: str | None = None) -> None:
        """Push the pretty login banner into the guest and kill the old MOTD.

        Everything is shipped base64-encoded, because `printf '%s' "a\\nb"`
        does NOT expand `\\n` in bash - the previous version wrote a single
        broken line into /root/.bashrc, which is why no banner appeared.
        Hooks are installed in /etc/profile.d, /root/.bashrc and
        /root/.bash_profile, and the web terminal runs `cloudy-login`, so the
        banner shows no matter how the guest image is set up.
        """
        try:
            with open(BANNER_SCRIPT, "rb") as fh:
                payload = base64.b64encode(fh.read()).decode("ascii")
        except OSError as exc:
            log.warning("banner script unavailable: %s", exc)
            return

        guest_lang = (
            self._guest_lang(container)
            if lang is None
            else ("ru" if str(lang).startswith("ru") else "en")
        )

        def b64(text: str) -> str:
            return base64.b64encode(text.encode("utf-8")).decode("ascii")

        # A guest keeps the limits it was created with, so prefer the
        # container's own CLOUDY_* variables and fall back to the live plan.
        live = PLAN_STORE.plan()
        env = self._guest_env(container)
        fields = {
            "lang": guest_lang,
            "ram": env.get("CLOUDY_RAM_MB") or live["ram_mb"],
            "disk": env.get("CLOUDY_DISK_GB") or live["disk_gb"],
            "cpu": env.get("CLOUDY_CPU") or live["cpu_cores"],
        }
        hook_b64 = b64(BANNER_HOOK % fields)
        login_b64 = b64(LOGIN_WRAPPER % fields)

        # Deleting single lines that merely *mention* cloudy-banner used to cut
        # lines out of the middle of the hook's `if` block and left an orphan
        # `fi` behind ("syntax error near unexpected token `fi'"). Instead, cut
        # everything from the first Cloudy-managed line to the end of the file
        # and append ONE line that sources the hook.
        cut = (
            "awk '/cloudy-banner|cloudy-login|CLOUDY_BANNER_SHOWN|CLOUDY_LANG|"
            "CLOUDY_RAM_MB|CLOUDY_DISK_GB|CLOUDY_CPU|alias banner=/{cut=1} "
            "cut!=1{print}'"
        )
        source_line = (
            "[ -f /etc/profile.d/00-cloudy-banner.sh ] && "
            ". /etc/profile.d/00-cloudy-banner.sh # cloudy-banner"
        )

        script = (
            "set -e; mkdir -p /usr/local/bin /etc/profile.d; "
            f"printf '%s' '{payload}' | base64 -d > {BANNER_PATH}; "
            f"chmod 755 {BANNER_PATH}; ln -sf {BANNER_PATH} /usr/local/bin/motd; "
            f"printf '%s' '{login_b64}' | base64 -d > {LOGIN_PATH}; "
            f"chmod 755 {LOGIN_PATH}; "
            f"printf '%s' '{hook_b64}' | base64 -d > {PROFILE_HOOK}; "
            f"chmod 644 {PROFILE_HOOK}; "
            # wipe every legacy welcome message so only the new banner shows
            ": > /etc/motd; rm -f /etc/update-motd.d/* 2>/dev/null || true; "
            ": > /etc/legal 2>/dev/null || true; "
            "touch /root/.hushlogin /root/.bashrc /root/.bash_profile; "
            # drop any previously injected (possibly broken) block
            "for f in /root/.bashrc /root/.bash_profile; do "
            f"{cut} \"$f\" > \"$f.cloudy\" 2>/dev/null && mv \"$f.cloudy\" \"$f\"; done; "
            f"printf '%s\\n' {json.dumps(source_line)} >> /root/.bashrc; "
            "printf '%s\\n' '[ -f /root/.bashrc ] && . /root/.bashrc' "
            ">> /root/.bash_profile; "
            # the rc files must stay syntactically valid
            "bash -n /root/.bashrc 2>/dev/null || echo 'bashrc-broken' >&2; "
            f"bash -n {PROFILE_HOOK} 2>/dev/null || echo 'hook-broken' >&2; "
            # sanity check: the banner must actually run inside the guest
            f"CLOUDY_LANG={guest_lang} {BANNER_PATH} >/dev/null 2>&1 || "
            "echo 'banner-selftest-failed' >&2; exit 0"
        )
        code, _out, err = self._exec(container, script)
        bad = any(
            marker in (err or "")
            for marker in ("banner-selftest-failed", "bashrc-broken", "hook-broken")
        )
        if code != 0 or bad:
            log.warning("banner install issue (%s): %s", code, err or "selftest failed")
        else:
            log.info("banner installed in %s (%s)", container.short_id, guest_lang)

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

        if action in ("start", "restart"):
            try:
                self._install_banner(container)
            except Exception as exc:  # pragma: no cover
                log.warning("could not refresh banner: %s", exc)

    async def power_action(self, user_id: int, action: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._action_sync, user_id, action)

    def _delete_sync(self, user_id: int) -> None:
        container = self._container(user_id)
        if container is not None:
            container.remove(force=True)
        self._state["servers"].pop(str(user_id), None)

        # Staff can own extra servers - promote the newest leftover so that
        # !manage keeps working after a delete.
        leftovers = sorted(
            (item for item in self._records_for(user_id) if item[0] != str(user_id)),
            key=lambda item: item[1].get("created_ts", 0),
            reverse=True,
        )
        for key, rec in leftovers:
            try:
                self.client.containers.get(rec["container_id"])
            except NotFound:
                self._state["servers"].pop(key, None)
                continue
            self._state["servers"].pop(key, None)
            self._state["servers"][str(user_id)] = rec
            break

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

        # Servers created before 1.3 Beta get a term as well.
        self._ensure_term(record)
        expires_ts = float(record.get("expires_ts") or 0)
        seconds_left = max(0.0, expires_ts - time.time()) if expires_ts else 0.0

        info = {
            "id": container.id,
            "short_id": container.id[:12],
            "name": record["name"],
            "hostname": record.get("hostname") or record["name"],
            "status": status,
            "os": record["os"],
            "ram_limit_mb": record["ram_mb"],
            "swap_mb": record.get("swap_mb", 0),
            "cpu_limit": record["cpu_cores"],
            "disk_gb": record["disk_gb"],
            "bandwidth": record["bandwidth"],
            "created_ts": record["created_ts"],
            "owner_id": record.get("owner_id", user_id),
            "owner_name": record.get("owner_name", ""),
            "ssh_user": record.get("ssh_user") or "root",
            # Account handed out with the server (!givevps), "root" otherwise.
            "login": record.get("login") or record.get("ssh_user") or "root",
            "term_days": int(record.get("term_days") or VPS_LIFETIME_DAYS),
            "expires_ts": expires_ts,
            "seconds_left": seconds_left,
            "days_left": int(seconds_left // 86400) if expires_ts else 0,
            "hours_left": int(seconds_left // 3600) if expires_ts else 0,
            "expired": bool(expires_ts and seconds_left <= 0),
            "unlimited_term": not expires_ts,
            "ram_used_mb": 0,
            "cpu_percent": 0.0,
            "net_rx_mb": 0.0,
            "net_tx_mb": 0.0,
            "uptime_seconds": 0,
            "has_sshx": bool(record.get("sshx")),
            "disk_used_gb": 0.0,
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
    # 30-day term (`!deploy` grants the VPS for VPS_LIFETIME_DAYS days)
    # ------------------------------------------------------------------
    def _ensure_term(self, record: dict) -> bool:
        """Add the term to servers created before 1.3 Beta. True when changed."""
        if VPS_LIFETIME_SECONDS <= 0:
            return False
        if float(record.get("expires_ts") or 0) > 0:
            return False
        created = float(record.get("created_ts") or time.time())
        record["expires_ts"] = created + VPS_LIFETIME_SECONDS
        record["term_days"] = int(record.get("term_days") or VPS_LIFETIME_DAYS)
        record.setdefault("warned_days", [])
        return True

    def terms(self) -> list[dict]:
        """Term info for every known server, the closest expiry first."""
        changed = False
        now = time.time()
        rows: list[dict] = []
        for key, record in list(self._state["servers"].items()):
            changed = self._ensure_term(record) or changed
            expires = float(record.get("expires_ts") or 0)
            rows.append(
                {
                    "key": key,
                    "owner_id": int(record.get("owner_id", 0) or 0),
                    "owner_name": record.get("owner_name", ""),
                    "name": record.get("name", ""),
                    "expires_ts": expires,
                    "seconds_left": max(0.0, expires - now) if expires else 0.0,
                    "days_left": int(max(0.0, expires - now) // 86400) if expires else 0,
                    "expired": bool(expires and expires <= now),
                    "warned_days": list(record.get("warned_days") or []),
                    "primary": key.isdigit(),
                }
            )
        if changed:
            self._save_state()
        return sorted(rows, key=lambda row: row["expires_ts"] or float("inf"))

    async def renew(self, user_id: int, days: float | None = None) -> float:
        """Extend the term (default: a whole new term). Returns the new expiry."""

        def _work() -> float:
            record = self.get_record(user_id)
            if record is None:
                raise VPSError(
                    "That user does not have a VPS. Use `!deploy` to create one."
                )
            span = float(VPS_LIFETIME_DAYS if days is None else days) * 86400.0
            if span <= 0:
                record["expires_ts"] = 0.0  # unlimited
            else:
                base = max(float(record.get("expires_ts") or 0), time.time())
                record["expires_ts"] = base + span
            record["term_days"] = int(record.get("term_days") or VPS_LIFETIME_DAYS)
            record["warned_days"] = []
            self._save_state()
            return float(record.get("expires_ts") or 0)

        async with self._lock:
            return await asyncio.to_thread(_work)

    async def mark_warned(self, user_id: int, day: int) -> None:
        """Remember that the "N days left" reminder was already sent."""

        def _work() -> None:
            record = self.get_record(user_id)
            if record is None:
                return
            warned = [int(d) for d in (record.get("warned_days") or [])]
            if int(day) not in warned:
                warned.append(int(day))
                record["warned_days"] = warned
                self._save_state()

        async with self._lock:
            await asyncio.to_thread(_work)

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


    # ------------------------------------------------------------------
    # sshx: browser terminal (second access method, no SSH client needed)
    # ------------------------------------------------------------------
    def _ensure_sshx_binary(self, container, lang: str = "en") -> None:
        """Make sure the sshx client exists in the guest (installs it once)."""
        code, _, _ = self._exec(
            container, f"command -v sshx >/dev/null 2>&1 || test -x {SSHX_BIN}"
        )
        if code == 0:
            return

        log.info("sshx missing in %s, installing at runtime", container.short_id)
        install = (
            "set -u; mkdir -p /usr/local/bin; "
            'arch="$(uname -m)"; '
            'case "$arch" in '
            "x86_64|amd64) target=x86_64-unknown-linux-musl ;; "
            "aarch64|arm64) target=aarch64-unknown-linux-musl ;; "
            "armv7*) target=armv7-unknown-linux-musleabihf ;; "
            "armv6*|armv5*) target=arm-unknown-linux-musleabihf ;; "
            '*) target="" ;; '
            "esac; "
            # 1) official statically linked build, straight from the bucket
            'if [ -n "$target" ]; then '
            f'url="{SSHX_BINARY_BASE}/sshx-$target.tar.gz"; '
            '(curl -fsSL "$url" -o /tmp/sshx.tgz || wget -qO /tmp/sshx.tgz "$url") '
            ">/dev/null 2>&1 && tar -xzf /tmp/sshx.tgz -C /usr/local/bin sshx "
            ">/dev/null 2>&1; fi; "
            # 2) fall back to the official installer script
            "if [ ! -x /usr/local/bin/sshx ] && ! command -v sshx >/dev/null 2>&1; then "
            f"(curl -sSf {SSHX_INSTALL_URL} | sh) >/dev/null 2>&1 || true; fi; "
            # 3) whatever it dropped somewhere else, put it on PATH
            'for p in /usr/bin/sshx "$HOME/.local/bin/sshx" ./sshx /root/sshx; do '
            '[ -x "$p" ] && [ ! -x /usr/local/bin/sshx ] && cp "$p" /usr/local/bin/sshx; '
            "done; "
            "chmod 755 /usr/local/bin/sshx 2>/dev/null; rm -f /tmp/sshx.tgz; "
            "command -v sshx >/dev/null 2>&1 || test -x /usr/local/bin/sshx"
        )
        code, out, err = self._exec(container, install)
        if code != 0:
            log.warning(
                "sshx install failed in %s: %s | %s", container.short_id, out, err
            )
            raise VPSError(t(lang, "sshx.install_failed"))

    def _sshx_link(self, container) -> str:
        """Last https://.../s/<id>#<key> link printed by sshx in the guest."""
        code, out, _ = self._exec(container, f"cat {SSHX_LOG} 2>/dev/null")
        if code != 0 or not out:
            return ""
        clean = ANSI_RE.sub("", out.replace("\r", "\n"))
        links = SSHX_URL_RE.findall(clean)
        return links[-1] if links else ""

    def _sshx_alive(self, container) -> bool:
        code, _, _ = self._exec(
            container, "pgrep -f '[s]shx' >/dev/null 2>&1 && echo yes"
        )
        return code == 0

    def _kill_sshx(self, container, wipe_log: bool = True) -> None:
        script = "pkill -f '[s]shx' >/dev/null 2>&1; sleep 0.4; "
        if wipe_log:
            script += f": > {SSHX_LOG} 2>/dev/null; "
        self._exec(container, script + "exit 0")

    def _start_sshx(self, container, budget: float) -> tuple[str, str]:
        """Start sshx detached and wait for its link. Returns (link, log tail).

        Flag support differs between client versions, so the variants degrade
        from "pretty" to "bare" instead of failing outright.
        """
        self._kill_sshx(container)
        server = f" --server {SSHX_SERVER}" if SSHX_SERVER else ""
        variants = [
            # cloudy-login shows the Cloudy banner in the browser terminal
            f"sshx{server} --quiet --shell {LOGIN_PATH}",
            f"sshx{server} --quiet",
            f"sshx{server}",
        ]
        per_try = max(10.0, budget / len(variants))
        tail = ""
        for command in variants:
            self._exec(
                container,
                "set -u; export TERM=xterm-256color; cd /root 2>/dev/null; "
                f": > {SSHX_LOG}; "
                f"setsid nohup {command} >> {SSHX_LOG} 2>&1 < /dev/null & "
                "sleep 1; exit 0",
            )

            deadline = time.time() + per_try
            while time.time() < deadline:
                link = self._sshx_link(container)
                if link:
                    log.info("sshx up in %s (%s)", container.short_id, command)
                    return link, ""
                _, tail, _ = self._exec(
                    container, f"tail -n 6 {SSHX_LOG} 2>/dev/null"
                )
                if not self._sshx_alive(container):
                    break  # client exited (unknown flag / no network) -> next
                time.sleep(1.0)

            self._kill_sshx(container, wipe_log=False)
        return "", tail

    def _sshx_sync(
        self, user_id: int, force_new: bool = False, lang: str = "en"
    ) -> str:
        if not SSHX_ENABLED:
            raise VPSError(t(lang, "sshx.disabled"))

        container = self._container(user_id)
        record = self.get_record(user_id)
        if container is None or record is None:
            raise VPSError(t(lang, "sshx.no_vps", prefix=COMMAND_PREFIX))

        container.reload()
        if container.status != "running":
            raise VPSError(t(lang, "sshx.not_running", prefix=COMMAND_PREFIX))

        # Re-use a live session unless the user explicitly asked for a new link.
        if record.get("sshx") and not force_new and self._sshx_alive(container):
            link = self._sshx_link(container)
            if link:
                if link != record.get("sshx"):
                    record["sshx"] = link
                    self._save_state()
                return link

        self._ensure_sshx_binary(container, lang)

        try:
            self._install_banner(container)
        except Exception as exc:  # pragma: no cover
            log.warning("could not refresh banner before sshx: %s", exc)

        link, tail = self._start_sshx(container, max(20.0, float(SSHX_TIMEOUT - 10)))
        if not link:
            raise VPSError(t(lang, "sshx.no_link", tail=(tail or "-")[-400:]))

        record["sshx"] = link
        record["sshx_ts"] = time.time()
        self._save_state()
        return link

    async def get_sshx(
        self, user_id: int, force_new: bool = False, lang: str = "en"
    ) -> str:
        """Browser-terminal link for this user's VPS."""
        return await asyncio.wait_for(
            asyncio.to_thread(self._sshx_sync, user_id, force_new, lang),
            timeout=SSHX_TIMEOUT + 30,
        )
