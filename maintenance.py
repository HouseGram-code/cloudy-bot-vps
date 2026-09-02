"""Maintenance mode storage for Cloudy VPS Bot.

When maintenance mode is ON, only owners (staff) can use the bot. Everyone
else gets a nice "we are working on the servers" message instead.
The state lives in a small JSON file so it survives restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

# `/app/data` only exists inside the Docker image: writing there from a host
# install raised "[Errno 13] Permission denied: '/app'". config resolves a
# writable data folder for every state file now.
try:  # keep working even next to a very old config.py
    from config import MAINTENANCE_FILE as _CONFIG_MAINTENANCE_FILE
except Exception:  # pragma: no cover
    _CONFIG_MAINTENANCE_FILE = ""

MAINTENANCE_FILE = (
    _CONFIG_MAINTENANCE_FILE
    or os.getenv("MAINTENANCE_FILE")
    or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "maintenance.json"
    )
)


class MaintenanceStore:
    def __init__(self, path: str = MAINTENANCE_FILE) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._state: dict = {
            "enabled": False,
            "reason": "",
            "since": 0.0,
            "by_id": 0,
            "by_name": "",
            "eta": "",
        }
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._state.update(
                    {k: data.get(k, v) for k, v in self._state.items()}
                )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
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
    def enabled(self) -> bool:
        return bool(self._state.get("enabled"))

    def state(self) -> dict:
        return dict(self._state)

    async def enable(
        self,
        moderator_id: int,
        moderator_name: str,
        reason: str = "",
        eta: str = "",
    ) -> dict:
        async with self._lock:
            self._state.update(
                {
                    "enabled": True,
                    "reason": reason.strip(),
                    "eta": eta.strip(),
                    "since": time.time(),
                    "by_id": int(moderator_id),
                    "by_name": moderator_name,
                }
            )
            self._save()
            return self.state()

    async def disable(self, moderator_id: int, moderator_name: str) -> dict:
        async with self._lock:
            self._state.update(
                {
                    "enabled": False,
                    "reason": "",
                    "eta": "",
                    "since": time.time(),
                    "by_id": int(moderator_id),
                    "by_name": moderator_name,
                }
            )
            self._save()
            return self.state()

    async def toggle(
        self, moderator_id: int, moderator_name: str, reason: str = ""
    ) -> dict:
        if self.enabled:
            return await self.disable(moderator_id, moderator_name)
        return await self.enable(moderator_id, moderator_name, reason)


# Shared instance used by the bot and by the views.
MAINTENANCE = MaintenanceStore()
