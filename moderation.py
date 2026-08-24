"""Ban / unban storage for Cloudy VPS Bot."""

from __future__ import annotations

import asyncio
import json
import os
import time

from config import BAN_FILE, is_owner


class ModerationError(Exception):
    """User-facing moderation error."""


class BanStore:
    def __init__(self, path: str = BAN_FILE) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._bans: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._bans = data.get("bans", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self._bans = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"bans": self._bans}, fh, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    def is_banned(self, user_id: int) -> bool:
        if is_owner(user_id):
            return False
        return str(user_id) in self._bans

    def get(self, user_id: int) -> dict | None:
        return self._bans.get(str(user_id))

    def all_bans(self) -> list[dict]:
        return sorted(self._bans.values(), key=lambda b: b.get("ts", 0), reverse=True)

    @property
    def count(self) -> int:
        return len(self._bans)

    # ------------------------------------------------------------------
    async def ban(
        self,
        user_id: int,
        reason: str,
        moderator_id: int,
        moderator_name: str,
        user_name: str = "",
    ) -> dict:
        if is_owner(user_id):
            raise ModerationError("This user is a bot owner and cannot be banned.")
        async with self._lock:
            if str(user_id) in self._bans:
                raise ModerationError("This user is already banned.")
            record = {
                "user_id": user_id,
                "user_name": user_name,
                "reason": reason or "No reason provided",
                "moderator_id": moderator_id,
                "moderator_name": moderator_name,
                "ts": time.time(),
            }
            self._bans[str(user_id)] = record
            self._save()
            return record

    async def unban(self, user_id: int) -> dict:
        async with self._lock:
            record = self._bans.pop(str(user_id), None)
            if record is None:
                raise ModerationError("This user is not banned.")
            self._save()
            return record
