"""Leaf wallet ("listiki") for Cloudy VPS Bot.

Every user has a balance of leaves. Leaves are the currency that keeps a free
VPS running:

* a brand new user starts with START_LEAVES leaves (3 by default);
* every hour a running VPS costs LEAF_COST_PER_HOUR leaf (1 by default);
* when the balance hits zero the VPS is stopped (never deleted) and the owner
  gets a DM, so nothing is lost - top up and start it again from `!manage`;
* `!bonus` (or the button on `!profile`) grants BONUS_LEAVES leaves once every
  BONUS_COOLDOWN_HOURS hours;
* staff can hand out leaves with `!give` or from the admin panel.

Balances live in a small JSON file so they survive restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import config


def _setting(name, default):
    """Read a setting from config, then the environment, then the default.

    Older config.py files do not know about the leaf economy; importing the
    names directly made the whole bot refuse to start on a partial update.
    """
    value = getattr(config, name, None)
    if value is None:
        value = os.getenv(name, default)
    return value


# 1.3 Beta: the leaf LIMIT is removed. LEAVES_ENABLED is False by default, so
# uptime is never charged and no server is stopped for an empty balance -
# leaves are just a counter shown by `!profile`, `!bonus` and `!give`.
LEAVES_ENABLED = bool(getattr(config, "LEAVES_ENABLED", False))
START_LEAVES = int(_setting("START_LEAVES", 100))
LEAF_COST_PER_HOUR = int(_setting("LEAF_COST_PER_HOUR", 1 if LEAVES_ENABLED else 0))
BONUS_LEAVES = int(_setting("BONUS_LEAVES", 25))
BONUS_COOLDOWN_HOURS = float(_setting("BONUS_COOLDOWN_HOURS", 24))


def _default_wallet_path() -> str:
    """Writable wallet path (never the container-only `/app/data`)."""
    resolver = getattr(config, "data_path", None)
    if callable(resolver):
        return resolver("wallet.json", "WALLET_FILE")
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "wallet.json"
    )


WALLET_FILE = str(getattr(config, "WALLET_FILE", "") or _default_wallet_path())

# Reported as "hours left" while the leaf limit is switched off.
UNLIMITED_HOURS = 1_000_000

# Hard limits so a typo in the admin panel cannot break the economy.
MAX_LEAVES = 1_000_000
MIN_GRANT = -MAX_LEAVES
MAX_GRANT = 100_000

HOUR = 3600.0
BONUS_COOLDOWN = float(BONUS_COOLDOWN_HOURS) * HOUR


def _clamp(value, low: int, high: int, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


class Wallet:
    """Persistent per-user leaf balances."""

    def __init__(self, path: str = WALLET_FILE, start: int = START_LEAVES) -> None:
        self.path = path
        self.start = int(start)
        self._lock = asyncio.Lock()
        self._users: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                users = data.get("users", data)
                if isinstance(users, dict):
                    for key, value in users.items():
                        if isinstance(value, dict):
                            self._users[str(key)] = self._normalize(value)
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"users": self._users}, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _normalize(self, raw: dict) -> dict:
        return {
            "leaves": _clamp(raw.get("leaves", self.start), 0, MAX_LEAVES, self.start),
            "earned": _clamp(raw.get("earned", 0), 0, MAX_LEAVES),
            "spent": _clamp(raw.get("spent", 0), 0, MAX_LEAVES),
            "bonus_ts": float(raw.get("bonus_ts", 0) or 0),
            "bonus_count": _clamp(raw.get("bonus_count", 0), 0, MAX_LEAVES),
            "charge_ts": float(raw.get("charge_ts", 0) or 0),
            "created_ts": float(raw.get("created_ts", 0) or time.time()),
            "name": str(raw.get("name", "") or ""),
        }

    # ------------------------------------------------------------------
    # lookups (sync, safe to call from embeds)
    # ------------------------------------------------------------------
    def _user(self, user_id: int, name: str = "") -> dict:
        key = str(int(user_id))
        user = self._users.get(key)
        if user is None:
            user = self._normalize({"leaves": self.start, "created_ts": time.time()})
            self._users[key] = user
            self._save()
        if name and user.get("name") != name:
            user["name"] = name
        return user

    def balance(self, user_id: int) -> int:
        return int(self._user(user_id)["leaves"])

    def state(self, user_id: int, name: str = "") -> dict:
        user = dict(self._user(user_id, name))
        user["bonus_in"] = self.bonus_in(user_id)
        user["bonus_ready"] = user["bonus_in"] <= 0
        user["hours_left"] = self.hours_left(user_id)
        user["cost"] = int(LEAF_COST_PER_HOUR)
        user["bonus_amount"] = int(BONUS_LEAVES)
        # True when leaves cannot limit anything (the 1.3 Beta default).
        user["unlimited"] = not self.limits_active()
        return user

    def limits_active(self) -> bool:
        """True only when leaves can really stop a server."""
        return bool(LEAVES_ENABLED) and int(LEAF_COST_PER_HOUR) > 0

    def bonus_in(self, user_id: int) -> float:
        """Seconds until the daily bonus can be claimed again (0 = ready)."""
        last = float(self._user(user_id).get("bonus_ts", 0) or 0)
        if last <= 0:
            return 0.0
        return max(0.0, (last + BONUS_COOLDOWN) - time.time())

    def bonus_ready(self, user_id: int) -> bool:
        return self.bonus_in(user_id) <= 0

    def bonus_at(self, user_id: int) -> float:
        """Unix timestamp when the bonus becomes available again."""
        last = float(self._user(user_id).get("bonus_ts", 0) or 0)
        return last + BONUS_COOLDOWN if last > 0 else time.time()

    def hours_left(self, user_id: int) -> int:
        """How many more hours a VPS can run with the current balance."""
        if not self.limits_active():
            return UNLIMITED_HOURS
        cost = max(1, int(LEAF_COST_PER_HOUR))
        return int(self.balance(user_id) // cost)

    def can_run(self, user_id: int) -> bool:
        """True when the user may run a VPS.

        The leaf limit is removed, so this is always True unless somebody
        turns the old hourly billing back on with LEAVES_ENABLED=1.
        """
        if not self.limits_active():
            return True
        return self.balance(user_id) >= max(1, int(LEAF_COST_PER_HOUR))

    def top(self, limit: int = 10) -> list[tuple[int, dict]]:
        rows = sorted(
            self._users.items(), key=lambda kv: int(kv[1].get("leaves", 0)), reverse=True
        )
        return [(int(uid), dict(data)) for uid, data in rows[:limit]]

    # ------------------------------------------------------------------
    # mutations
    # ------------------------------------------------------------------
    async def ensure(self, user_id: int, name: str = "") -> dict:
        """Make sure the account exists (new users get their starting leaves)."""
        async with self._lock:
            user = self._user(user_id, name)
            self._save()
            return dict(user)

    async def add(self, user_id: int, amount: int, name: str = "") -> int:
        """Add (or, with a negative amount, remove) leaves. Returns the balance."""
        delta = _clamp(amount, MIN_GRANT, MAX_GRANT)
        async with self._lock:
            user = self._user(user_id, name)
            before = int(user["leaves"])
            user["leaves"] = _clamp(before + delta, 0, MAX_LEAVES)
            if delta > 0:
                user["earned"] = _clamp(user["earned"] + delta, 0, MAX_LEAVES)
            else:
                user["spent"] = _clamp(user["spent"] + (before - user["leaves"]), 0, MAX_LEAVES)
            self._save()
            return int(user["leaves"])

    async def claim_bonus(self, user_id: int, name: str = "") -> dict:
        """Try to claim the daily bonus.

        Returns {"ok": bool, "amount": int, "balance": int, "retry_in": float,
        "ready_at": float}.
        """
        async with self._lock:
            user = self._user(user_id, name)
            now = time.time()
            last = float(user.get("bonus_ts", 0) or 0)
            wait = max(0.0, (last + BONUS_COOLDOWN) - now) if last > 0 else 0.0
            if wait > 0:
                return {
                    "ok": False,
                    "amount": 0,
                    "balance": int(user["leaves"]),
                    "retry_in": wait,
                    "ready_at": last + BONUS_COOLDOWN,
                }
            amount = int(BONUS_LEAVES)
            user["leaves"] = _clamp(int(user["leaves"]) + amount, 0, MAX_LEAVES)
            user["earned"] = _clamp(user["earned"] + amount, 0, MAX_LEAVES)
            user["bonus_ts"] = now
            user["bonus_count"] = int(user.get("bonus_count", 0)) + 1
            self._save()
            return {
                "ok": True,
                "amount": amount,
                "balance": int(user["leaves"]),
                "retry_in": BONUS_COOLDOWN,
                "ready_at": now + BONUS_COOLDOWN,
            }

    async def start_billing(self, user_id: int, name: str = "") -> None:
        """Reset the billing clock (VPS created / started right now)."""
        async with self._lock:
            user = self._user(user_id, name)
            user["charge_ts"] = time.time()
            self._save()

    async def stop_billing(self, user_id: int) -> None:
        """Stop the billing clock (VPS stopped or deleted)."""
        async with self._lock:
            user = self._user(user_id)
            user["charge_ts"] = 0.0
            self._save()

    async def charge_due(self, user_id: int, name: str = "") -> dict:
        """Charge every full hour that passed since the last charge.

        Returns {"charged": int, "balance": int, "empty": bool} where `empty`
        means the user can no longer pay for the next hour.
        """
        if not self.limits_active():
            # Leaf limit removed: uptime is free and nothing is ever charged.
            return {
                "charged": 0,
                "balance": self.balance(user_id),
                "empty": False,
            }

        cost = max(1, int(LEAF_COST_PER_HOUR))
        async with self._lock:
            user = self._user(user_id, name)
            now = time.time()
            last = float(user.get("charge_ts", 0) or 0)
            if last <= 0:
                user["charge_ts"] = now
                self._save()
                return {
                    "charged": 0,
                    "balance": int(user["leaves"]),
                    "empty": int(user["leaves"]) < cost,
                }

            hours = int((now - last) // HOUR)
            if hours <= 0:
                return {
                    "charged": 0,
                    "balance": int(user["leaves"]),
                    "empty": int(user["leaves"]) < cost,
                }

            want = hours * cost
            have = int(user["leaves"])
            paid = min(want, have)
            user["leaves"] = _clamp(have - paid, 0, MAX_LEAVES)
            user["spent"] = _clamp(user["spent"] + paid, 0, MAX_LEAVES)
            user["charge_ts"] = last + hours * HOUR
            self._save()
            return {
                "charged": paid,
                "balance": int(user["leaves"]),
                "empty": int(user["leaves"]) < cost,
            }


# Shared instance used by the bot, the views and the VPS manager.
WALLET = Wallet()
