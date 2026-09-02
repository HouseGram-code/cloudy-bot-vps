"""Configuration for Cloudy VPS Bot."""

import os
import tempfile

from dotenv import load_dotenv

from token_store import get_builtin_token

load_dotenv()

# ---------------------------------------------------------------------------
# Writable data directory  (fix for: [Errno 13] Permission denied: '/app')
# ---------------------------------------------------------------------------
# Every state file used to be hardcoded to `/app/data/...` - a path that only
# exists *inside* the Docker image. When the bot runs straight on a host
# (`python3 bot.py`) or as a non-root user, `os.makedirs("/app/data")` raises
# `[Errno 13] Permission denied: '/app'`, which is exactly why every deploy
# failed. The data directory is now resolved once at import time and the first
# candidate we can really write to wins:
#   1. $DATA_DIR             explicit override
#   2. /app/data             inside the container
#   3. <bot folder>/data     normal host install
#   4. ~/.cloudy-vps-bot     read-only install folder
#   5. /tmp/cloudy-vps-bot   last resort, so start-up can never crash
_HERE = os.path.dirname(os.path.abspath(__file__))


def _is_writable(path: str) -> bool:
    """True when files can be created inside `path` (creating it if needed)."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".cloudy-write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _resolve_data_dir() -> str:
    candidates: list[str] = []
    explicit = (os.getenv("DATA_DIR") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    candidates += [
        "/app/data",
        os.path.join(_HERE, "data"),
        os.path.join(os.path.expanduser("~"), ".cloudy-vps-bot"),
        os.path.join(tempfile.gettempdir(), "cloudy-vps-bot"),
    ]
    for path in candidates:
        if _is_writable(path):
            return path
    return os.path.abspath(".")


DATA_DIR = _resolve_data_dir()


def data_path(name: str, env_var: str = "") -> str:
    """Absolute path of one state file inside DATA_DIR.

    An explicit override (e.g. `STATE_FILE=/srv/cloudy/state.json`) is honoured
    as long as its folder is writable; otherwise we silently fall back to
    DATA_DIR, so a stale `/app/data/...` value can never break start-up again.
    """
    if env_var:
        override = (os.getenv(env_var) or "").strip()
        if override:
            override = os.path.abspath(os.path.expanduser(override))
            if _is_writable(os.path.dirname(override) or "."):
                return override
    return os.path.join(DATA_DIR, name)

# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------
BOT_NAME = "Cloudy VPS Bot"
BOT_VERSION = "1.4 Beta"
# Pretty test-build badge shown next to the version ("dev", "rc", "stable"...).
# It is cosmetic only: BOT_BUILD=stable simply changes the label.
BOT_BUILD = (os.getenv("BOT_BUILD", "dev") or "dev").strip()
BOT_BUILD_BADGE = (
    os.getenv("BOT_BUILD_BADGE", "").strip() or f"\u25c6 {BOT_BUILD} build"
)
BOT_VERSION_FULL = f"{BOT_VERSION} \u2022 {BOT_BUILD_BADGE}"
BOT_FOOTER = f"{BOT_NAME} • v{BOT_VERSION} • {BOT_BUILD_BADGE}"

COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# ---------------------------------------------------------------------------
# Language (RU / EN)
# ---------------------------------------------------------------------------
# DEFAULT_LANG is used until a user picks their own with `!lang`.
# Each choice is stored in LANG_FILE so it survives restarts.
DEFAULT_LANG = (os.getenv("DEFAULT_LANG", "en").lower() if os.getenv("DEFAULT_LANG") else "en")
if DEFAULT_LANG not in ("en", "ru"):
    DEFAULT_LANG = "en"
LANG_FILE = data_path("languages.json", "LANG_FILE")

# The token ships with the project (obfuscated in token_store.py) so the bot
# runs out of the box. An explicit DISCORD_TOKEN env var always takes priority.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or get_builtin_token()

# ---------------------------------------------------------------------------
# Staff / owners
# ---------------------------------------------------------------------------
# Owners can always use every command, can never be banned, and bypass limits.
DEFAULT_OWNERS = [1264586393594630239]


def _parse_ids(raw: str) -> list[int]:
    out = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


OWNER_IDS = _parse_ids(os.getenv("OWNER_IDS", "")) or DEFAULT_OWNERS


def is_owner(user_id: int) -> bool:
    return int(user_id) in OWNER_IDS


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------
# Access links are NEVER posted in a channel. They are sent to the user's
# direct messages; if DMs are closed the bot falls back to an ephemeral reply
# that only that user can see.
ACCESS_TO_DM_ONLY = os.getenv("ACCESS_TO_DM_ONLY", "1") not in ("0", "false", "False")

# ---------------------------------------------------------------------------
# Rules (max 5) - shown by !rules and before every deployment
# ---------------------------------------------------------------------------
RULES: list[tuple[str, str]] = [
    (
        "One free server per person",
        "Alt accounts to farm extra servers are not allowed. Duplicates get removed.",
    ),
    (
        "No attacks or abuse",
        "No DDoS, port scanning, brute force, spam, phishing or proxy/VPN services.",
    ),
    (
        "No crypto mining or resource farming",
        "Miners, stress tests and 100% CPU loops are killed and the account is banned.",
    ),
    (
        "No illegal content",
        "Nothing pirated, stolen, malicious, or against Discord's Terms of Service.",
    ),
    (
        "Free tier is best effort",
        "Servers may be restarted, wiped or removed at any time. Keep your own backups.",
    ),
][:5]

# ---------------------------------------------------------------------------
# Colors / emojis (visual style)
# ---------------------------------------------------------------------------
COLOR_PRIMARY = 0x5865F2   # blurple
COLOR_SUCCESS = 0x57F287   # green
COLOR_WARNING = 0xFEE75C   # yellow
COLOR_ERROR = 0xED4245     # red
COLOR_NEUTRAL = 0x2B2D31   # dark

EMOJI = {
    "cloud": "\u2601\ufe0f",
    "rocket": "\U0001F680",
    "gear": "\u2699\ufe0f",
    "ram": "\U0001F9E0",
    "cpu": "\U0001F5A5\ufe0f",
    "disk": "\U0001F4BE",
    "net": "\U0001F310",
    "os": "\U0001F427",
    "key": "\U0001F511",
    "clock": "\u23F1\ufe0f",
    "online": "\U0001F7E9",
    "offline": "\U0001F7E5",
    "pending": "\U0001F7E8",
    "check": "\u2705",
    "cross": "\u274C",
    "spark": "\u2728",
    "lock": "\U0001F512",
    "mail": "\U0001F4EC",
    "scroll": "\U0001F4DC",
    "hammer": "\U0001F528",
    "shield": "\U0001F6E1\ufe0f",
    "leaf": "\U0001F343",
    "gift": "\U0001F381",
    "wallet": "\U0001F45B",
    "user": "\U0001F464",
    "id": "\U0001F194",
    "link": "\U0001F517",
    "web": "\U0001F310",
}

# ---------------------------------------------------------------------------
# Free VPS plan
# ---------------------------------------------------------------------------
PLAN = {
    "name": "Free Tier",
    "os": "Ubuntu 22.04 LTS (Jammy Jellyfish)",
    "os_short": "ubuntu-22.04",
    # Defaults of the free tier. Staff can change them at runtime with
    # `!plan` or the buttons in `!admin` (see plan_store.py).
    "ram_mb": int(os.getenv("VPS_RAM_MB", "2048")),
    "swap_mb": int(os.getenv("VPS_SWAP_MB", "1024")),
    "cpu_cores": float(os.getenv("VPS_CPU_CORES", "2")),
    "disk_gb": int(os.getenv("VPS_DISK_GB", "20")),
    "bandwidth": os.getenv("VPS_BANDWIDTH", "Unmetered (fair use)"),
    "location": os.getenv("VPS_LOCATION", "EU • Docker Host"),
    "access": "sshx web terminal",
}

# ---------------------------------------------------------------------------
# Docker / runtime
# ---------------------------------------------------------------------------
VPS_IMAGE = os.getenv("VPS_IMAGE", "cloudy-vps:ubuntu-22.04")
CONTAINER_PREFIX = os.getenv("CONTAINER_PREFIX", "cloudy-vps")
MAX_VPS_PER_USER = int(os.getenv("MAX_VPS_PER_USER", "1"))
# Global capacity of the host: how many VPS may exist at the same time (5/5).
# Staff can change it at runtime from the admin panel or with `!slots`.
TOTAL_VPS_SLOTS = int(os.getenv("TOTAL_VPS_SLOTS", "5"))
STATE_FILE = data_path("vps_state.json", "STATE_FILE")
BAN_FILE = data_path("bans.json", "BAN_FILE")
SLOTS_FILE = data_path("slots.json", "SLOTS_FILE")
# Live resource plan (RAM / swap / vCPU / disk) edited from `!admin` or
# `!plan`. Deleting the file resets the plan to the values above.
PLAN_FILE = data_path("plan.json", "PLAN_FILE")
MAINTENANCE_FILE = data_path("maintenance.json", "MAINTENANCE_FILE")

# ---------------------------------------------------------------------------
# VPS term: a free server is granted for 30 days
# ---------------------------------------------------------------------------
# `!deploy` hands out the VPS for VPS_LIFETIME_DAYS days. The bot reminds the
# owner before the term ends and then frees the slot automatically.
VPS_LIFETIME_DAYS = int(os.getenv("VPS_LIFETIME_DAYS", "30") or 30)
VPS_LIFETIME_SECONDS = max(0, VPS_LIFETIME_DAYS) * 86400
# "delete" frees the slot when the term is over, "stop" only powers it off.
VPS_EXPIRY_ACTION = (os.getenv("VPS_EXPIRY_ACTION", "delete") or "delete").strip().lower()
# Days before the end of the term when the owner receives a DM reminder.
VPS_EXPIRY_WARN_DAYS = [
    int(day.strip())
    for day in os.getenv("VPS_EXPIRY_WARN_DAYS", "7,3,1").split(",")
    if day.strip().isdigit()
] or [7, 3, 1]

# ---------------------------------------------------------------------------
# Leaf economy ("listiki") - THE LIMIT IS REMOVED
# ---------------------------------------------------------------------------
# Leaves no longer gate anything: a server is granted for VPS_LIFETIME_DAYS
# days and is never stopped because the balance hit zero. Leaves stay only as
# a cosmetic counter for `!profile` / `!bonus` / `!give`.
# Set LEAVES_ENABLED=1 if you ever want the old hourly billing back.
LEAVES_ENABLED = (os.getenv("LEAVES_ENABLED", "0") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
START_LEAVES = int(os.getenv("START_LEAVES", "100"))
LEAF_COST_PER_HOUR = int(
    os.getenv("LEAF_COST_PER_HOUR", "1" if LEAVES_ENABLED else "0")
)
BONUS_LEAVES = int(os.getenv("BONUS_LEAVES", "25"))
BONUS_COOLDOWN_HOURS = int(os.getenv("BONUS_COOLDOWN_HOURS", "24"))
WALLET_FILE = data_path("wallet.json", "WALLET_FILE")

# DNS servers given to guest containers so package mirrors and sshx resolve.
VPS_DNS = [s.strip() for s in os.getenv("VPS_DNS", "1.1.1.1,8.8.8.8").split(",") if s.strip()]

# ---------------------------------------------------------------------------
# sshx - browser terminal (the only way into a VPS)
# ---------------------------------------------------------------------------
# sshx gives every VPS a link like https://sshx.io/s/<id>#<key>. The part after
# "#" is the encryption key: it stays in the browser and never reaches the
# server, so the link itself is the credential (we only DM it).
# It only needs plain outbound HTTPS: no SSH client, no keys, no open ports.
SSHX_ENABLED = os.getenv("SSHX_ENABLED", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
SSHX_TIMEOUT = int(os.getenv("SSHX_TIMEOUT", "90"))
SSHX_INSTALL_URL = os.getenv("SSHX_INSTALL_URL", "https://sshx.io/get")
SSHX_BINARY_BASE = os.getenv("SSHX_BINARY_BASE", "https://sshx.s3.amazonaws.com")
# Optional self-hosted sshx server (empty = the public mesh).
SSHX_SERVER = os.getenv("SSHX_SERVER", "").strip()

ANIM_DELAY = float(os.getenv("ANIM_DELAY", "0.9"))

# ---------------------------------------------------------------------------
# 1.4 Beta (dev): regions, OS images, abuse guard, service status
# ---------------------------------------------------------------------------
# State files of the new subsystems. They live in DATA_DIR like everything
# else, so regions, the deploy switch and the guard counters survive an
# update, a restart or a full container rebuild.
LOCATIONS_FILE = data_path("locations.json", "LOCATIONS_FILE")
DEPLOY_LOCK_FILE = data_path("deploy_lock.json", "DEPLOY_LOCK_FILE")
GUARD_FILE = data_path("guard.json", "GUARD_FILE")

# --- pickable systems (step 2 of the deploy wizard) -------------------------
# `available` is derived from OS_AVAILABLE: an image only shows up as ready
# when it is actually built on this host (see images/<id>/Dockerfile).
OS_AVAILABLE = {
    item.strip()
    for item in os.getenv("OS_AVAILABLE", "ubuntu-22.04").split(",")
    if item.strip()
}
OS_CHOICES: list[dict] = [
    {
        "id": "ubuntu-22.04",
        "label": "Ubuntu 22.04 LTS",
        "codename": "Jammy Jellyfish",
        "emoji": "\U0001F427",
        "image": os.getenv("VPS_IMAGE_2204", VPS_IMAGE),
        "recommended": True,
    },
    {
        "id": "ubuntu-24.04",
        "label": "Ubuntu 24.04 LTS",
        "codename": "Noble Numbat",
        "emoji": "\U0001F427",
        "image": os.getenv("VPS_IMAGE_2404", "cloudy-vps:ubuntu-24.04"),
        "recommended": False,
    },
    {
        "id": "ubuntu-20.04",
        "label": "Ubuntu 20.04 LTS",
        "codename": "Focal Fossa",
        "emoji": "\U0001F427",
        "image": os.getenv("VPS_IMAGE_2004", "cloudy-vps:ubuntu-20.04"),
        "recommended": False,
    },
]
for _choice in OS_CHOICES:
    _choice["available"] = _choice["id"] in OS_AVAILABLE
    _choice["full"] = f"{_choice['label']} ({_choice['codename']})"
OS_BY_ID = {item["id"]: item for item in OS_CHOICES}
DEFAULT_OS_ID = (os.getenv("DEFAULT_OS", "ubuntu-22.04") or "").strip()
if DEFAULT_OS_ID not in OS_BY_ID or not OS_BY_ID[DEFAULT_OS_ID]["available"]:
    DEFAULT_OS_ID = "ubuntu-22.04"

# --- abuse guard ------------------------------------------------------------
# Kills crypto miners / attack tools inside the guests, warns the owner and
# stops the server on a repeat strike. See guard.py.
GUARD_ENABLED = (os.getenv("GUARD_ENABLED", "1") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
GUARD_INTERVAL = int(os.getenv("GUARD_INTERVAL", "120"))
GUARD_STRIKES = int(os.getenv("GUARD_STRIKES", "2"))
GUARD_STOP_ON_STRIKE = (
    os.getenv("GUARD_STOP_ON_STRIKE", "1") or "1"
).strip().lower() not in ("0", "false", "no", "off")
GUARD_BAN_ON_STRIKE = (
    os.getenv("GUARD_BAN_ON_STRIKE", "0") or "0"
).strip().lower() in ("1", "true", "yes", "on")
GUARD_CPU_WARN = float(os.getenv("GUARD_CPU_WARN", "97"))
GUARD_CPU_STRIKES = int(os.getenv("GUARD_CPU_STRIKES", "5"))

# Extra kernel capabilities dropped from every guest (anti-abuse hardening).
GUEST_CAP_DROP = [
    item.strip()
    for item in os.getenv(
        "GUEST_CAP_DROP",
        "NET_RAW,NET_ADMIN,SYS_ADMIN,SYS_MODULE,SYS_TIME,SYS_RAWIO,MKNOD,AUDIT_WRITE",
    ).split(",")
    if item.strip()
]
GUEST_MAX_PROCS = int(os.getenv("GUEST_MAX_PROCS", "384"))
GUEST_MAX_FILES = int(os.getenv("GUEST_MAX_FILES", "4096"))

# --- service status ---------------------------------------------------------
# `!status` renders a PNG with Pillow; set STATUS_IMAGE=0 for text only.
STATUS_IMAGE = (os.getenv("STATUS_IMAGE", "1") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
