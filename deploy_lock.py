"""Deploy switch for Cloudy VPS Bot (1.4 Beta · dev).

Staff can close and open `!deploy` without touching maintenance mode:

    !deploy off  "disk upgrade"     -> nobody can create a new server
    !deploy off  "upgrade" 30       -> closed for 30 minutes, then auto-open
    !deploy on                      -> open again

Everything else (`!manage`, `!sshx`, `!status`, ...) keeps working, and the
state lives in a small JSON file so a restart or an update never re-opens
deployments by accident.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

try:  # keep working even next to a very old config.py
    from config import DEPLOY_LOCK_FILE as _CONFIG_DEPLOY_LOCK_FILE
except Exception:  # pragma: no cover
    _CONFIG_DEPLOY_LOCK_FILE = ""

DEPLOY_LOCK_FILE = (
    _CONFIG_DEPLOY_LOCK_FILE
    or os.getenv("DEPLOY_LOCK_FILE")
    or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "deploy_lock.json"
    )
)


class DeployLockStore:
    """Persistent \"deployments are closed\" flag."""

    def __init__(self, path: str = DEPLOY_LOCK_FILE) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._state: dict = {
            "closed": False,
            "reason": "",
            "since": 0.0,
            "until": 0.0,
            "by_id": 0,
            "by_name": "",
        }
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._state.update({k: data.get(k, v) for k, v in self._state.items()})
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    @property
    def closed(self) -> bool:
        """True while `!deploy` is closed (a timed lock expires by itself)."""
        if not bool(self._state.get("closed")):
            return False
        until = float(self._state.get("until") or 0.0)
        if until and until <= time.time():
            self._state.update({"closed": False, "reason": "", "until": 0.0})
            self._save()
            return False
        return True

    @property
    def open(self) -> bool:
        return not self.closed

    def seconds_left(self) -> int:
        until = float(self._state.get("until") or 0.0)
        if not until:
            return 0
        return int(max(0.0, until - time.time()))

    def state(self) -> dict:
        data = dict(self._state)
        data["closed"] = self.closed
        data["seconds_left"] = self.seconds_left()
        data["minutes_left"] = (
            max(1, int(data["seconds_left"] // 60 + 1)) if data["seconds_left"] else 0
        )
        return data

    # ------------------------------------------------------------------
    async def close(
        self,
        moderator_id: int = 0,
        moderator_name: str = "",
        reason: str = "",
        minutes: int = 0,
    ) -> dict:
        async with self._lock:
            now = time.time()
            self._state.update(
                {
                    "closed": True,
                    "reason": (reason or "").strip(),
                    "since": now,
                    "until": now + max(0, int(minutes)) * 60.0 if minutes else 0.0,
                    "by_id": int(moderator_id),
                    "by_name": moderator_name,
                }
            )
            self._save()
            return self.state()

    async def reopen(self, moderator_id: int = 0, moderator_name: str = "") -> dict:
        async with self._lock:
            self._state.update(
                {
                    "closed": False,
                    "reason": "",
                    "since": time.time(),
                    "until": 0.0,
                    "by_id": int(moderator_id),
                    "by_name": moderator_name,
                }
            )
            self._save()
            return self.state()

    async def toggle(
        self,
        moderator_id: int = 0,
        moderator_name: str = "",
        reason: str = "",
        minutes: int = 0,
    ) -> dict:
        if self.closed:
            return await self.reopen(moderator_id, moderator_name)
        return await self.close(moderator_id, moderator_name, reason, minutes)


# Shared instance used by the bot, the views and the admin panel.
DEPLOY_LOCK = DeployLockStore()
