"""Configuration for Cloudy VPS Bot."""

import os

from dotenv import load_dotenv

from token_store import get_builtin_token

load_dotenv()

# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------
BOT_NAME = "Cloudy VPS Bot"
BOT_VERSION = "1.0 Beta"
BOT_FOOTER = f"{BOT_NAME} • v{BOT_VERSION}"

COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# The token ships with the project (obfuscated in token_store.py) so the bot
# runs out of the box. An explicit DISCORD_TOKEN env var always takes priority.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or get_builtin_token()

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
}

# ---------------------------------------------------------------------------
# Free VPS plan
# ---------------------------------------------------------------------------
PLAN = {
    "name": "Free Tier",
    "os": "Ubuntu 22.04 LTS (Jammy Jellyfish)",
    "os_short": "ubuntu-22.04",
    "ram_mb": int(os.getenv("VPS_RAM_MB", "1024")),
    "swap_mb": int(os.getenv("VPS_SWAP_MB", "512")),
    "cpu_cores": float(os.getenv("VPS_CPU_CORES", "1")),
    "disk_gb": int(os.getenv("VPS_DISK_GB", "10")),
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
STATE_FILE = os.getenv("STATE_FILE", "/app/data/vps_state.json")

# How long to wait for a tmate session string before giving up (seconds)
TMATE_TIMEOUT = int(os.getenv("TMATE_TIMEOUT", "60"))

# Deployment animation speed (seconds per frame)
ANIM_DELAY = float(os.getenv("ANIM_DELAY", "0.9"))
