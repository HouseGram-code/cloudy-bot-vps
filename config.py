"""Configuration for Cloudy VPS Bot."""

import os

from dotenv import load_dotenv

from token_store import get_builtin_token

load_dotenv()

# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------
BOT_NAME = "Cloudy VPS Bot"
BOT_VERSION = "1.2 Beta"
BOT_FOOTER = f"{BOT_NAME} • v{BOT_VERSION}"

COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# ---------------------------------------------------------------------------
# Language (RU / EN)
# ---------------------------------------------------------------------------
# DEFAULT_LANG is used until a user picks their own with `!lang`.
# Each choice is stored in LANG_FILE so it survives restarts.
DEFAULT_LANG = (os.getenv("DEFAULT_LANG", "en").lower() if os.getenv("DEFAULT_LANG") else "en")
if DEFAULT_LANG not in ("en", "ru"):
    DEFAULT_LANG = "en"
LANG_FILE = os.getenv("LANG_FILE", "/app/data/languages.json")

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
# SSH credentials are NEVER posted in a channel. They are sent to the user's
# direct messages; if DMs are closed the bot falls back to an ephemeral reply
# that only that user can see.
SSH_TO_DM_ONLY = os.getenv("SSH_TO_DM_ONLY", "1") not in ("0", "false", "False")

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
    "access": "tmate SSH",
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
STATE_FILE = os.getenv("STATE_FILE", "/app/data/vps_state.json")
BAN_FILE = os.getenv("BAN_FILE", "/app/data/bans.json")
SLOTS_FILE = os.getenv("SLOTS_FILE", "/app/data/slots.json")
# Live resource plan (RAM / swap / vCPU / disk) edited from `!admin` or
# `!plan`. Deleting the file resets the plan to the values above.
PLAN_FILE = os.getenv("PLAN_FILE", "/app/data/plan.json")

# ---------------------------------------------------------------------------
# Leaf economy ("listiki")
# ---------------------------------------------------------------------------
# Leaves keep a free VPS alive: a new user gets START_LEAVES, and every hour of
# uptime costs LEAF_COST_PER_HOUR. At zero the VPS is stopped, never deleted.
# The daily bonus gives BONUS_LEAVES once every BONUS_COOLDOWN_HOURS hours.
START_LEAVES = int(os.getenv("START_LEAVES", "3"))
LEAF_COST_PER_HOUR = int(os.getenv("LEAF_COST_PER_HOUR", "1"))
BONUS_LEAVES = int(os.getenv("BONUS_LEAVES", "25"))
BONUS_COOLDOWN_HOURS = int(os.getenv("BONUS_COOLDOWN_HOURS", "24"))
WALLET_FILE = os.getenv("WALLET_FILE", "/app/data/wallet.json")

# DNS servers given to guest containers so tmate.io always resolves.
VPS_DNS = [s.strip() for s in os.getenv("VPS_DNS", "1.1.1.1,8.8.8.8").split(",") if s.strip()]

# How long to wait for a tmate session string before giving up (seconds)
TMATE_TIMEOUT = int(os.getenv("TMATE_TIMEOUT", "90"))

# ---------------------------------------------------------------------------
# tmate relay
# ---------------------------------------------------------------------------
# Many hosts / firewalls only allow "normal" outbound ports, so tmate's default
# TCP 2200 is blocked. ssh.tmate.io also accepts connections on 22 (and 443 on
# most nodes), so we try several ports in order and use the first that works.
TMATE_SERVER_HOST = os.getenv("TMATE_SERVER_HOST", "ssh.tmate.io")
TMATE_PORTS = [
    int(p.strip())
    for p in os.getenv("TMATE_PORTS", "2200,22,443").split(",")
    if p.strip().isdigit()
] or [2200]

# Only needed when TMATE_SERVER_HOST points at a self-hosted tmate-ssh-server.
# Get them from that server's `tmate-ssh-server -h` output / install log.
TMATE_RSA_FINGERPRINT = os.getenv("TMATE_RSA_FINGERPRINT", "").strip()
TMATE_ED25519_FINGERPRINT = os.getenv("TMATE_ED25519_FINGERPRINT", "").strip()

# Deployment animation speed (seconds per frame)
ANIM_DELAY = float(os.getenv("ANIM_DELAY", "0.9"))
