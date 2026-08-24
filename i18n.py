"""Bilingual (RU / EN) strings and per-user language storage.

Usage:
    from i18n import LangStore, t
    langs = LangStore()
    lang = langs.get(user_id)          # "ru" or "en"
    t(lang, "deploy.title")
"""

from __future__ import annotations

import json
import os
import threading

DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en").lower()
if DEFAULT_LANG not in ("en", "ru"):
    DEFAULT_LANG = "en"

LANG_FILE = os.getenv("LANG_FILE", "/app/data/languages.json")

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "flag": "\U0001F1EC\U0001F1E7"},
    "ru": {"name": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439", "flag": "\U0001F1F7\U0001F1FA"},
}


def normalize(lang: str | None) -> str:
    lang = (lang or "").lower().strip()
    if lang.startswith("ru"):
        return "ru"
    if lang.startswith("en"):
        return "en"
    return DEFAULT_LANG


class LangStore:
    """Remembers each user's language choice in a small JSON file."""

    def __init__(self, path: str = LANG_FILE) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self._data = {str(k): normalize(v) for k, v in json.load(fh).items()}
        except (FileNotFoundError, json.JSONDecodeError, AttributeError, OSError):
            self._data = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def get(self, user_id: int | None) -> str:
        if user_id is None:
            return DEFAULT_LANG
        return self._data.get(str(user_id), DEFAULT_LANG)

    def set(self, user_id: int, lang: str) -> str:
        lang = normalize(lang)
        with self._lock:
            self._data[str(user_id)] = lang
            self._save()
        return lang


# ---------------------------------------------------------------------------
# Strings: STRINGS[key][lang]
# ---------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    "generic.error_title": {"en": "Something went wrong", "ru": "\u0427\u0442\u043e-\u0442\u043e \u043f\u043e\u0448\u043b\u043e \u043d\u0435 \u0442\u0430\u043a"},
    "generic.online": {"en": "Online", "ru": "\u0412 \u0441\u0435\u0442\u0438"},
    "generic.offline": {"en": "Offline", "ru": "\u041e\u0442\u043a\u043b\u044e\u0447\u0451\u043d"},
    "generic.server_id": {"en": "Server ID", "ru": "ID \u0441\u0435\u0440\u0432\u0435\u0440\u0430"},
    "generic.hostname": {"en": "Hostname", "ru": "\u0418\u043c\u044f \u0445\u043e\u0441\u0442\u0430"},
    "generic.status": {"en": "Status", "ru": "\u0421\u0442\u0430\u0442\u0443\u0441"},
    "generic.created": {"en": "Created", "ru": "\u0421\u043e\u0437\u0434\u0430\u043d"},
    "generic.reason": {"en": "Reason", "ru": "\u041f\u0440\u0438\u0447\u0438\u043d\u0430"},
    "generic.ram": {"en": "RAM", "ru": "\u041e\u0417\u0423"},
    "generic.cpu": {"en": "CPU", "ru": "\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440"},
    "generic.disk": {"en": "Disk", "ru": "\u0414\u0438\u0441\u043a"},
    "generic.os": {"en": "OS", "ru": "\u041e\u0421"},
    "generic.network": {"en": "Network", "ru": "\u0421\u0435\u0442\u044c"},
    "generic.uptime": {"en": "Uptime", "ru": "\u0412\u0440\u0435\u043c\u044f \u0440\u0430\u0431\u043e\u0442\u044b"},
    "generic.bandwidth": {"en": "Bandwidth", "ru": "\u0422\u0440\u0430\u0444\u0438\u043a"},

    "rules.title": {"en": "Free VPS \u2014 Rules", "ru": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS \u2014 \u041f\u0440\u0430\u0432\u0438\u043b\u0430"},
    "rules.desc": {
        "en": "By deploying a server you agree to all of the rules below.\nBreaking any of them means an instant **ban** and server removal.",
        "ru": "\u0421\u043e\u0437\u0434\u0430\u0432\u0430\u044f \u0441\u0435\u0440\u0432\u0435\u0440, \u0432\u044b \u0441\u043e\u0433\u043b\u0430\u0448\u0430\u0435\u0442\u0435\u0441\u044c \u0441\u043e \u0432\u0441\u0435\u043c\u0438 \u043f\u0440\u0430\u0432\u0438\u043b\u0430\u043c\u0438 \u043d\u0438\u0436\u0435.\n\u041b\u044e\u0431\u043e\u0435 \u043d\u0430\u0440\u0443\u0448\u0435\u043d\u0438\u0435 \u2014 \u043c\u0433\u043d\u043e\u0432\u0435\u043d\u043d\u044b\u0439 **\u0431\u0430\u043d** \u0438 \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u0430.",
    },

    "deploy.title": {"en": "Free VPS \u2014 Deployment", "ru": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS \u2014 \u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435"},
    "deploy.desc": {
        "en": "Hey {user}, you are about to deploy a **free VPS** on **{os}**.\nReview the specifications below and press **Start** when you are ready.",
        "ru": "{user}, \u0441\u0435\u0439\u0447\u0430\u0441 \u0432\u044b \u0441\u043e\u0437\u0434\u0430\u0434\u0438\u0442\u0435 **\u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS** \u043d\u0430 **{os}**.\n\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0438 \u043d\u0438\u0436\u0435 \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u0421\u0442\u0430\u0440\u0442**.",
    },
    "deploy.memory": {"en": "Memory (RAM)", "ru": "\u041f\u0430\u043c\u044f\u0442\u044c (RAM)"},
    "deploy.swap": {"en": "swap", "ru": "\u043f\u043e\u0434\u043a\u0430\u0447\u043a\u0430"},
    "deploy.processor": {"en": "Processor", "ru": "\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440"},
    "deploy.fair_share": {"en": "fair-share", "ru": "\u0431\u0435\u0437 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u0439"},
    "deploy.storage": {"en": "Storage", "ru": "\u0425\u0440\u0430\u043d\u0438\u043b\u0438\u0449\u0435"},
    "deploy.os": {"en": "Operating system", "ru": "\u041e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430"},
    "deploy.access": {"en": "Access", "ru": "\u0414\u043e\u0441\u0442\u0443\u043f"},
    "deploy.access_value": {"en": "**tmate SSH**\n`sent to your DMs`", "ru": "**tmate SSH**\n`\u043f\u0440\u0438\u0441\u043b\u0430\u043d \u0432 \u041b\u0421`"},
    "deploy.plan": {"en": "Plan", "ru": "\u0422\u0430\u0440\u0438\u0444"},
    "deploy.location": {"en": "Location", "ru": "\u041b\u043e\u043a\u0430\u0446\u0438\u044f"},
    "deploy.rules_field": {
        "en": "Pressing **Start** means you accept all **{count} rules**.\nPress **Rules** to read them first.",
        "ru": "\u041d\u0430\u0436\u0430\u0442\u0438\u0435 **\u0421\u0442\u0430\u0440\u0442** = \u0441\u043e\u0433\u043b\u0430\u0441\u0438\u0435 \u0441\u043e \u0432\u0441\u0435\u043c\u0438 **{count} \u043f\u0440\u0430\u0432\u0438\u043b\u0430\u043c\u0438**.\n\u041d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u0440\u0430\u0432\u0438\u043b\u0430**, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0442\u044c \u0438\u0445.",
    },
    "deploy.privacy": {"en": "Privacy", "ru": "\u041f\u0440\u0438\u0432\u0430\u0442\u043d\u043e\u0441\u0442\u044c"},
    "deploy.privacy_value": {
        "en": "Your SSH command is **never posted in a channel** \u2014 only in your DMs.",
        "ru": "\u041a\u043e\u043c\u0430\u043d\u0434\u0430 SSH **\u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0443\u0435\u0442\u0441\u044f \u0432 \u043a\u0430\u043d\u0430\u043b\u0435** \u2014 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 \u041b\u0421.",
    },
    "deploy.failed": {"en": "Deployment failed: `{error}`", "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440: `{error}`"},

    "progress.title": {"en": "Deploying your VPS\u2026", "ru": "\u0421\u043e\u0437\u0434\u0430\u0451\u043c \u0432\u0430\u0448 VPS\u2026"},
    "progress.build_log": {"en": "Build log", "ru": "\u0416\u0443\u0440\u043d\u0430\u043b \u0441\u0431\u043e\u0440\u043a\u0438"},
    "progress.init": {"en": "Initializing\u2026", "ru": "\u0418\u043d\u0438\u0446\u0438\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f\u2026"},
    "progress.finishing": {"en": "Finishing up\u2026", "ru": "\u0417\u0430\u0432\u0435\u0440\u0448\u0430\u0435\u043c\u2026"},
    "stage.alloc": {"en": "Allocating resources\u2026", "ru": "\u0412\u044b\u0434\u0435\u043b\u044f\u0435\u043c \u0440\u0435\u0441\u0443\u0440\u0441\u044b\u2026"},
    "stage.image": {"en": "Pulling Ubuntu 22.04 LTS image\u2026", "ru": "\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u043c \u043e\u0431\u0440\u0430\u0437 Ubuntu 22.04 LTS\u2026"},
    "stage.disk": {"en": "Creating virtual disk\u2026", "ru": "\u0421\u043e\u0437\u0434\u0430\u0451\u043c \u0432\u0438\u0440\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0439 \u0434\u0438\u0441\u043a\u2026"},
    "stage.boot": {"en": "Booting the machine\u2026", "ru": "\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u043c \u043c\u0430\u0448\u0438\u043d\u0443\u2026"},
    "stage.net": {"en": "Configuring network\u2026", "ru": "\u041d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0435\u043c \u0441\u0435\u0442\u044c\u2026"},
    "stage.apt": {"en": "Installing base packages\u2026", "ru": "\u0423\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u0435\u043c \u0431\u0430\u0437\u043e\u0432\u044b\u0435 \u043f\u0430\u043a\u0435\u0442\u044b\u2026"},
    "stage.tmate": {"en": "Opening tmate SSH session\u2026", "ru": "\u041e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u043c SSH-\u0441\u0435\u0441\u0441\u0438\u044e tmate\u2026"},
    "stage.health": {"en": "Running final health checks\u2026", "ru": "\u0424\u0438\u043d\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0441\u0435\u0440\u0432\u0438\u0441\u043e\u0432\u2026"},
    "success.title": {"en": "VPS deployed successfully!", "ru": "VPS \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u0441\u043e\u0437\u0434\u0430\u043d!"},
    "success.desc": {
        "en": "Your free VPS is **online** and ready to use.\nManage it any time with `{prefix}manage`.",
        "ru": "\u0412\u0430\u0448 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS **\u0432 \u0441\u0435\u0442\u0438** \u0438 \u0433\u043e\u0442\u043e\u0432 \u043a \u0440\u0430\u0431\u043e\u0442\u0435.\n\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u2014 \u043a\u043e\u043c\u0430\u043d\u0434\u0430 `{prefix}manage`.",
    },
    "success.ssh_field": {"en": "SSH access (tmate)", "ru": "\u0414\u043e\u0441\u0442\u0443\u043f SSH (tmate)"},

    "ssh.dm_title": {"en": "Your VPS \u2014 SSH access", "ru": "\u0412\u0430\u0448 VPS \u2014 \u0434\u043e\u0441\u0442\u0443\u043f SSH"},
    "ssh.dm_desc": {
        "en": "Server **{name}** \u2022 `{sid}`\n\nPaste this in your terminal to connect as `root`:\n```bash\n{ssh}\n```",
        "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 **{name}** \u2022 `{sid}`\n\n\u0412\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0432 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u043a\u0430\u043a `root`:\n```bash\n{ssh}\n```",
    },
    "ssh.system": {"en": "System", "ru": "\u0421\u0438\u0441\u0442\u0435\u043c\u0430"},
    "ssh.keep_private": {"en": "Keep it private", "ru": "\u041d\u0438\u043a\u043e\u043c\u0443 \u043d\u0435 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0439\u0442\u0435"},
    "ssh.keep_private_value": {
        "en": "Anyone with this line gets **full root access** to your server.\nStopping or restarting the VPS invalidates it \u2014 press **Get SSH** in `{prefix}manage` for a fresh one.",
        "ru": "\u041b\u044e\u0431\u043e\u0439, \u043a\u0442\u043e \u0443\u0432\u0438\u0434\u0438\u0442 \u044d\u0442\u0443 \u0441\u0442\u0440\u043e\u043a\u0443, \u043f\u043e\u043b\u0443\u0447\u0438\u0442 **\u043f\u043e\u043b\u043d\u044b\u0439 root-\u0434\u043e\u0441\u0442\u0443\u043f**.\n\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a VPS \u0434\u0435\u043b\u0430\u0435\u0442 \u0435\u0451 \u043d\u0435\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0439 \u2014 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u0432 `{prefix}manage`.",
    },
    "ssh.dm_failed_title": {"en": "I cannot DM you", "ru": "\u041d\u0435 \u043c\u043e\u0433\u0443 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c \u0432\u0430\u043c \u0432 \u041b\u0421"},
    "ssh.dm_failed_desc": {
        "en": "Your SSH command is only ever sent privately, but your DMs are closed.\n\n**Fix it:** Server settings \u2192 *Privacy Settings* \u2192 enable **Direct Messages**, then press **Get SSH** again.",
        "ru": "\u041a\u043e\u043c\u0430\u043d\u0434\u0430 SSH \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u043b\u0438\u0447\u043d\u043e, \u0430 \u0432\u0430\u0448\u0438 \u041b\u0421 \u0437\u0430\u043a\u0440\u044b\u0442\u044b.\n\n**\u041a\u0430\u043a \u0438\u0441\u043f\u0440\u0430\u0432\u0438\u0442\u044c:** \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 \u2192 *\u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c* \u2192 \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u0435 **\u041b\u0438\u0447\u043d\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f** \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u0441\u043d\u043e\u0432\u0430.",
    },
    "ssh.sent_dm": {"en": "Sent to your **DMs** \u2014 check your private messages.", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u0432 **\u041b\u0421** \u2014 \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043b\u0438\u0447\u043d\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f."},
    "ssh.sent_ephemeral": {"en": "Sent privately (DMs are closed, so it was shown only to you here).", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u043f\u0440\u0438\u0432\u0430\u0442\u043d\u043e (\u041b\u0421 \u0437\u0430\u043a\u0440\u044b\u0442\u044b \u2014 \u0432\u0438\u0434\u043d\u043e \u0442\u043e\u043b\u044c\u043a\u043e \u0432\u0430\u043c)."},
    "ssh.slow": {"en": "Session is taking longer than usual. Press **Get SSH** in a moment.", "ru": "\u0421\u0435\u0441\u0441\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u0451\u0442\u0441\u044f \u0434\u043e\u043b\u044c\u0448\u0435 \u043e\u0431\u044b\u0447\u043d\u043e\u0433\u043e. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u0447\u0435\u0440\u0435\u0437 \u043c\u0438\u043d\u0443\u0442\u0443."},
    "ssh.retry": {"en": "Could not open the session yet \u2014 press **Get SSH** to retry.\nDetails were sent to you privately.", "ru": "\u041f\u043e\u043a\u0430 \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u0435\u0441\u0441\u0438\u044e \u2014 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u0435\u0449\u0451 \u0440\u0430\u0437.\n\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u043b\u0438\u0447\u043d\u043e."},
    "ssh.timeout": {"en": "tmate took too long to respond. Try again.", "ru": "tmate \u043d\u0435 \u043e\u0442\u0432\u0435\u0442\u0438\u043b \u0432\u043e\u0432\u0440\u0435\u043c\u044f. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430."},
    "ssh.check_dms_title": {"en": "Check your DMs", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u041b\u0421"},
    "ssh.check_dms_desc": {"en": "Your SSH command was sent privately \u2014 it is never posted in a channel.", "ru": "\u041a\u043e\u043c\u0430\u043d\u0434\u0430 SSH \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430 \u043b\u0438\u0447\u043d\u043e \u2014 \u0432 \u043a\u0430\u043d\u0430\u043b\u0435 \u043e\u043d\u0430 \u043d\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0443\u0435\u0442\u0441\u044f."},

    "manage.title": {"en": "VPS Control Panel", "ru": "\u041f\u0430\u043d\u0435\u043b\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f VPS"},
    "manage.desc": {
        "en": "**{name}** \u2022 {status}\nUse the buttons below to control your server.",
        "ru": "**{name}** \u2022 {status}\n\u041a\u043d\u043e\u043f\u043a\u0438 \u043d\u0438\u0436\u0435 \u0443\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c.",
    },
    "manage.memory": {"en": "Memory", "ru": "\u041f\u0430\u043c\u044f\u0442\u044c"},
    "manage.allocated_offline": {"en": "**{value}** allocated \u2022 `server offline`", "ru": "\u0432\u044b\u0434\u0435\u043b\u0435\u043d\u043e **{value}** \u2022 `\u0441\u0435\u0440\u0432\u0435\u0440 \u043e\u0442\u043a\u043b\u044e\u0447\u0451\u043d`"},
    "manage.ssh_running": {"en": "Press **Get SSH** \u2014 the command is sent to your **DMs** only.", "ru": "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u2014 \u043a\u043e\u043c\u0430\u043d\u0434\u0430 \u043f\u0440\u0438\u0434\u0451\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 **\u041b\u0421**."},
    "manage.ssh_stopped": {"en": "Start the server first, then press **Get SSH**.", "ru": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440, \u0437\u0430\u0442\u0435\u043c \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH**."},
    "manage.now_status": {"en": "Your VPS `{name}` is now **{status}**.", "ru": "\u0412\u0430\u0448 VPS `{name}` \u0442\u0435\u043f\u0435\u0440\u044c **{status}**."},
    "manage.session_closed": {"en": "\nThe old SSH session was closed \u2014 press **Get SSH** for a new one.", "ru": "\n\u0421\u0442\u0430\u0440\u0430\u044f SSH-\u0441\u0435\u0441\u0441\u0438\u044f \u0437\u0430\u043a\u0440\u044b\u0442\u0430 \u2014 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH** \u0434\u043b\u044f \u043d\u043e\u0432\u043e\u0439."},
    "manage.started": {"en": "Server started", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u0437\u0430\u043f\u0443\u0449\u0435\u043d"},
    "manage.stopped": {"en": "Server stopped", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d"},
    "manage.restarted": {"en": "Server restarted", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0449\u0435\u043d"},
    "manage.already_own": {"en": "You already own a VPS \u2014 here is your control panel.", "ru": "\u0423 \u0432\u0430\u0441 \u0443\u0436\u0435 \u0435\u0441\u0442\u044c VPS \u2014 \u0432\u043e\u0442 \u043f\u0430\u043d\u0435\u043b\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f."},

    "btn.start": {"en": "Start", "ru": "\u0421\u0442\u0430\u0440\u0442"},
    "btn.stop": {"en": "Stop", "ru": "\u0421\u0442\u043e\u043f"},
    "btn.restart": {"en": "Restart", "ru": "\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a"},
    "btn.ssh": {"en": "Get SSH", "ru": "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c SSH"},
    "btn.refresh": {"en": "Refresh", "ru": "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c"},
    "btn.rules": {"en": "Rules", "ru": "\u041f\u0440\u0430\u0432\u0438\u043b\u0430"},
    "btn.cancel": {"en": "Cancel", "ru": "\u041e\u0442\u043c\u0435\u043d\u0430"},

    "cancel.title": {"en": "Deployment cancelled", "ru": "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e"},
    "cancel.desc": {"en": "No server was created. Run `{prefix}deploy` whenever you are ready.", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u043d\u0435 \u0441\u043e\u0437\u0434\u0430\u043d. \u041d\u0430\u0431\u0435\u0440\u0438\u0442\u0435 `{prefix}deploy`, \u043a\u043e\u0433\u0434\u0430 \u0431\u0443\u0434\u0435\u0442\u0435 \u0433\u043e\u0442\u043e\u0432\u044b."},
    "panel.not_yours_title": {"en": "Not your panel", "ru": "\u042d\u0442\u043e \u043d\u0435 \u0432\u0430\u0448\u0430 \u043f\u0430\u043d\u0435\u043b\u044c"},
    "panel.not_yours": {"en": "This panel belongs to someone else. Run the command yourself to get your own.", "ru": "\u042d\u0442\u0430 \u043f\u0430\u043d\u0435\u043b\u044c \u043f\u0440\u0438\u043d\u0430\u0434\u043b\u0435\u0436\u0438\u0442 \u0434\u0440\u0443\u0433\u043e\u043c\u0443 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e. \u0412\u044b\u0437\u043e\u0432\u0438\u0442\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u0443 \u0441\u0430\u043c\u0438."},

    "destroy.title": {"en": "VPS destroyed", "ru": "VPS \u0443\u0434\u0430\u043b\u0451\u043d"},
    "destroy.desc": {"en": "Your server and its disk were removed. You can `{prefix}deploy` a new one.", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u0438 \u0435\u0433\u043e \u0434\u0438\u0441\u043a \u0443\u0434\u0430\u043b\u0435\u043d\u044b. \u041c\u043e\u0436\u043d\u043e \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439: `{prefix}deploy`."},

    "ping.title": {"en": "Pong!", "ru": "\u041f\u043e\u043d\u0433!"},
    "ping.desc": {"en": "Gateway latency: **{ms} ms**", "ru": "\u0417\u0430\u0434\u0435\u0440\u0436\u043a\u0430 \u0448\u043b\u044e\u0437\u0430: **{ms} \u043c\u0441**"},

    "lang.title": {"en": "Language / \u042f\u0437\u044b\u043a", "ru": "\u042f\u0437\u044b\u043a / Language"},
    "lang.desc": {"en": "Choose the language the bot should use for you.\nCurrent: **{current}**", "ru": "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u044f\u0437\u044b\u043a \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430 \u0431\u043e\u0442\u0430.\n\u0421\u0435\u0439\u0447\u0430\u0441: **{current}**"},
    "lang.changed_title": {"en": "Language updated", "ru": "\u042f\u0437\u044b\u043a \u0438\u0437\u043c\u0435\u043d\u0451\u043d"},
    "lang.changed": {"en": "The bot will talk to you in **English** from now on.", "ru": "\u0422\u0435\u043f\u0435\u0440\u044c \u0431\u043e\u0442 \u0431\u0443\u0434\u0435\u0442 \u043e\u0431\u0449\u0430\u0442\u044c\u0441\u044f \u0441 \u0432\u0430\u043c\u0438 \u043d\u0430 **\u0440\u0443\u0441\u0441\u043a\u043e\u043c**."},
    "lang.select_placeholder": {"en": "Select a language\u2026", "ru": "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u044f\u0437\u044b\u043a\u2026"},

    "mod.banned_title": {"en": "User banned", "ru": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u0437\u0430\u0431\u0430\u043d\u0435\u043d"},
    "mod.banned_desc": {"en": "<@{uid}> can no longer use the bot.", "ru": "<@{uid}> \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0431\u043e\u0442\u043e\u043c."},
    "mod.user_id": {"en": "User ID", "ru": "ID \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f"},
    "mod.moderator": {"en": "Moderator", "ru": "\u041c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440"},
    "mod.server": {"en": "Server", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440"},
    "mod.stopped_auto": {"en": "Stopped automatically", "ru": "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438"},
    "mod.no_server": {"en": "No running server", "ru": "\u0417\u0430\u043f\u0443\u0449\u0435\u043d\u043d\u043e\u0433\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0430 \u043d\u0435\u0442"},
    "mod.unbanned_title": {"en": "User unbanned", "ru": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u0440\u0430\u0437\u0431\u0430\u043d\u0435\u043d"},
    "mod.unbanned_desc": {"en": "<@{uid}> can use the bot again.", "ru": "<@{uid}> \u0441\u043d\u043e\u0432\u0430 \u043c\u043e\u0436\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0431\u043e\u0442\u043e\u043c."},
    "mod.prev_reason": {"en": "Previous reason", "ru": "\u041f\u0440\u0435\u0436\u043d\u044f\u044f \u043f\u0440\u0438\u0447\u0438\u043d\u0430"},
    "mod.banlist_title": {"en": "Ban list", "ru": "\u0421\u043f\u0438\u0441\u043e\u043a \u0431\u0430\u043d\u043e\u0432"},
    "mod.banlist_desc": {"en": "**{count}** banned user(s).", "ru": "\u0417\u0430\u0431\u0430\u043d\u0435\u043d\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: **{count}**."},
    "mod.banlist_empty": {"en": "Nobody is banned.", "ru": "\u041d\u0438\u043a\u0442\u043e \u043d\u0435 \u0437\u0430\u0431\u0430\u043d\u0435\u043d."},
    "mod.you_banned_title": {"en": "You are banned", "ru": "\u0412\u044b \u0437\u0430\u0431\u0430\u043d\u0435\u043d\u044b"},
    "mod.you_banned_desc": {
        "en": "You can no longer deploy or manage servers with this bot.\nContact the staff if you think this is a mistake.",
        "ru": "\u0412\u044b \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442\u0435 \u0441\u043e\u0437\u0434\u0430\u0432\u0430\u0442\u044c \u0438 \u0443\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440\u0430\u043c\u0438 \u0447\u0435\u0440\u0435\u0437 \u044d\u0442\u043e\u0433\u043e \u0431\u043e\u0442\u0430.\n\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438, \u0435\u0441\u043b\u0438 \u0441\u0447\u0438\u0442\u0430\u0435\u0442\u0435 \u044d\u0442\u043e \u043e\u0448\u0438\u0431\u043a\u043e\u0439.",
    },
    "mod.banned_at": {"en": "Banned", "ru": "\u0417\u0430\u0431\u0430\u043d\u0435\u043d"},

    "help.desc": {"en": "Free VPS hosting, right from Discord.\nVersion **{version}**", "ru": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS-\u0445\u043e\u0441\u0442\u0438\u043d\u0433 \u043f\u0440\u044f\u043c\u043e \u0438\u0437 Discord.\n\u0412\u0435\u0440\u0441\u0438\u044f **{version}**"},
    "help.deploy": {"en": "Show the free plan specifications and deploy a new VPS.", "ru": "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0438 \u0442\u0430\u0440\u0438\u0444\u0430 \u0438 \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439 VPS."},
    "help.manage": {"en": "Live server info + Start / Stop / Restart / Get SSH buttons.", "ru": "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 \u0438 \u043a\u043d\u043e\u043f\u043a\u0438 \u0421\u0442\u0430\u0440\u0442 / \u0421\u0442\u043e\u043f / \u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a / SSH."},
    "help.rules": {"en": "The {count} rules of the free tier.", "ru": "{count} \u043f\u0440\u0430\u0432\u0438\u043b\u0430 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e\u0433\u043e \u0442\u0430\u0440\u0438\u0444\u0430."},
    "help.destroy": {"en": "Delete your VPS.", "ru": "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0432\u0430\u0448 VPS."},
    "help.ping": {"en": "Check bot latency.", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0437\u0430\u0434\u0435\u0440\u0436\u043a\u0443 \u0431\u043e\u0442\u0430."},
    "help.lang": {"en": "Switch the bot language (Russian / English).", "ru": "\u041f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u044f\u0437\u044b\u043a \u0431\u043e\u0442\u0430 (\u0440\u0443\u0441\u0441\u043a\u0438\u0439 / \u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u0438\u0439)."},
    "help.staff": {"en": "Staff only", "ru": "\u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0430\u0434\u043c\u0438\u043d\u043e\u0432"},
    "help.usage_ban": {"en": "Usage: `{prefix}ban <@user|id> [reason]`", "ru": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}ban <@\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c|id> [\u043f\u0440\u0438\u0447\u0438\u043d\u0430]`"},
    "help.missing_user": {"en": "Missing user", "ru": "\u041d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c"},
    "help.admin": {"en": "Admin panel: maintenance mode, live stats.", "ru": "\u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c: \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b \u0438 \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430."},

    # ---- maintenance mode (user side) ----
    "maint.title": {"en": "Scheduled maintenance", "ru": "\u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b"},
    "maint.headline": {
        "en": "We are polishing the cloud right now.",
        "ru": "\u041c\u044b \u0441\u0435\u0439\u0447\u0430\u0441 \u043f\u0440\u0438\u0432\u043e\u0434\u0438\u043c \u043e\u0431\u043b\u0430\u043a\u043e \u0432 \u043f\u043e\u0440\u044f\u0434\u043e\u043a.",
    },
    "maint.body": {
        "en": "The hosting panel is temporarily closed while the team works on the servers.\nYour VPS and your files are **safe** \u2014 nothing is deleted.\n\nCome back a little later and press `{prefix}deploy` again.",
        "ru": "\u041f\u0430\u043d\u0435\u043b\u044c \u0445\u043e\u0441\u0442\u0438\u043d\u0433\u0430 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u0437\u0430\u043a\u0440\u044b\u0442\u0430, \u043a\u043e\u043c\u0430\u043d\u0434\u0430 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043d\u0430\u0434 \u0441\u0435\u0440\u0432\u0435\u0440\u0430\u043c\u0438.\n\u0412\u0430\u0448 VPS \u0438 \u0432\u0430\u0448\u0438 \u0444\u0430\u0439\u043b\u044b **\u0432 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438** \u2014 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u0443\u0434\u0430\u043b\u044f\u0435\u0442\u0441\u044f.\n\n\u0417\u0430\u0433\u043b\u044f\u043d\u0438\u0442\u0435 \u043d\u0435\u043c\u043d\u043e\u0433\u043e \u043f\u043e\u0437\u0436\u0435 \u0438 \u0441\u043d\u043e\u0432\u0430 \u043d\u0430\u0431\u0435\u0440\u0438\u0442\u0435 `{prefix}deploy`.",
    },
    "maint.what": {"en": "What is happening", "ru": "\u0427\u0442\u043e \u043f\u0440\u043e\u0438\u0441\u0445\u043e\u0434\u0438\u0442"},
    "maint.default_reason": {
        "en": "Routine upgrade of the host and the VPS images.",
        "ru": "\u041f\u043b\u0430\u043d\u043e\u0432\u043e\u0435 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u0445\u043e\u0441\u0442\u0430 \u0438 \u043e\u0431\u0440\u0430\u0437\u043e\u0432 VPS.",
    },
    "maint.since": {"en": "Started", "ru": "\u041d\u0430\u0447\u0430\u043b\u043e"},
    "maint.eta": {"en": "Expected back", "ru": "\u041e\u0436\u0438\u0434\u0430\u0435\u043c\u043e\u0435 \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0435\u043d\u0438\u0435"},
    "maint.available": {"en": "Still available", "ru": "\u0412\u0441\u0451 \u0435\u0449\u0451 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442"},
    "maint.available_value": {
        "en": "`{prefix}rules` \u2022 `{prefix}lang` \u2022 `{prefix}help` \u2014 and your running servers keep running.",
        "ru": "`{prefix}rules` \u2022 `{prefix}lang` \u2022 `{prefix}help` \u2014 \u0430 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u043d\u044b\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u044b \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u044e\u0442 \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c.",
    },
    "maint.footer_note": {"en": "Thanks for your patience \u2014 the cloud will be back shortly.", "ru": "\u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u0442\u0435\u0440\u043f\u0435\u043d\u0438\u0435 \u2014 \u043e\u0431\u043b\u0430\u043a\u043e \u0441\u043a\u043e\u0440\u043e \u0432\u0435\u0440\u043d\u0451\u0442\u0441\u044f."},

    # ---- admin panel ----
    "admin.title": {"en": "Admin Panel", "ru": "\u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c"},
    "admin.desc": {
        "en": "Staff controls for **{bot}**.\nMaintenance mode closes the bot for everyone except staff.",
        "ru": "\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 **{bot}** \u0434\u043b\u044f \u0430\u0434\u043c\u0438\u043d\u043e\u0432.\n\u0420\u0435\u0436\u0438\u043c \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0445 \u0440\u0430\u0431\u043e\u0442 \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0435\u0442 \u0431\u043e\u0442\u0430 \u0434\u043b\u044f \u0432\u0441\u0435\u0445, \u043a\u0440\u043e\u043c\u0435 \u0430\u0434\u043c\u0438\u043d\u043e\u0432.",
    },
    "admin.mode": {"en": "Maintenance mode", "ru": "\u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b"},
    "admin.mode_on": {"en": "**ON** \u2014 only staff can use the bot", "ru": "**\u0412\u041a\u041b** \u2014 \u0431\u043e\u0442\u043e\u043c \u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0430\u0434\u043c\u0438\u043d\u044b"},
    "admin.mode_off": {"en": "**OFF** \u2014 the bot is open to everyone", "ru": "**\u0412\u042b\u041a\u041b** \u2014 \u0431\u043e\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0432\u0441\u0435\u043c"},
    "admin.changed_by": {"en": "Changed by", "ru": "\u0418\u0437\u043c\u0435\u043d\u0438\u043b"},
    "admin.servers": {"en": "Deployed servers", "ru": "\u0421\u043e\u0437\u0434\u0430\u043d\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432"},
    "admin.bans": {"en": "Bans", "ru": "\u0411\u0430\u043d\u043e\u0432"},
    "admin.hint": {"en": "Tip", "ru": "\u041f\u043e\u0434\u0441\u043a\u0430\u0437\u043a\u0430"},
    "admin.hint_value": {
        "en": "`{prefix}maintenance on <reason>` \u2022 `{prefix}maintenance off` \u2022 `{prefix}admin`",
        "ru": "`{prefix}maintenance on <\u043f\u0440\u0438\u0447\u0438\u043d\u0430>` \u2022 `{prefix}maintenance off` \u2022 `{prefix}admin`",
    },
    "admin.btn_on": {"en": "Enable maintenance", "ru": "\u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0442\u0435\u0445\u0440\u0430\u0431\u043e\u0442\u044b"},
    "admin.btn_off": {"en": "Disable maintenance", "ru": "\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0442\u0435\u0445\u0440\u0430\u0431\u043e\u0442\u044b"},
    "admin.btn_preview": {"en": "Preview notice", "ru": "\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440"},
    "admin.btn_refresh": {"en": "Refresh", "ru": "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c"},
    "admin.enabled_title": {"en": "Maintenance mode enabled", "ru": "\u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u044b"},
    "admin.enabled_desc": {
        "en": "From now on only staff can use the bot. Everyone else sees the maintenance notice.",
        "ru": "\u0422\u0435\u043f\u0435\u0440\u044c \u0431\u043e\u0442\u043e\u043c \u043c\u043e\u0433\u0443\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0430\u0434\u043c\u0438\u043d\u044b. \u041e\u0441\u0442\u0430\u043b\u044c\u043d\u044b\u0435 \u0432\u0438\u0434\u044f\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e \u0442\u0435\u0445\u0440\u0430\u0431\u043e\u0442\u0430\u0445.",
    },
    "admin.disabled_title": {"en": "Maintenance mode disabled", "ru": "\u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u044b"},
    "admin.disabled_desc": {
        "en": "The bot is open to everyone again. Have fun!",
        "ru": "\u0411\u043e\u0442 \u0441\u043d\u043e\u0432\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0432\u0441\u0435\u043c. \u041f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435\u0441\u044c!",
    },
    "admin.usage": {
        "en": "Usage: `{prefix}maintenance on [reason]` or `{prefix}maintenance off`",
        "ru": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}maintenance on [\u043f\u0440\u0438\u0447\u0438\u043d\u0430]` \u0438\u043b\u0438 `{prefix}maintenance off`",
    },
    "admin.only_staff": {"en": "This panel is for staff only.", "ru": "\u042d\u0442\u0430 \u043f\u0430\u043d\u0435\u043b\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0430\u0434\u043c\u0438\u043d\u043e\u0432."},
    # ---- capacity / slots ----
    "admin.capacity": {"en": "Capacity", "ru": "\u0421\u043b\u043e\u0442\u044b"},
    "admin.running": {"en": "Running", "ru": "\u0417\u0430\u043f\u0443\u0449\u0435\u043d\u043e"},
    "admin.stopped": {"en": "Stopped", "ru": "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e"},
    "admin.btn_slot_plus": {"en": "+1 slot", "ru": "+1 \u0441\u043b\u043e\u0442"},
    "admin.btn_slot_minus": {"en": "-1 slot", "ru": "-1 \u0441\u043b\u043e\u0442"},
    "slots.title": {"en": "Host capacity", "ru": "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0445\u043e\u0441\u0442\u0430"},
    "slots.desc": {
        "en": "**{used}/{total}** slots in use \u2022 **{free}** free",
        "ru": "\u0417\u0430\u043d\u044f\u0442\u043e **{used}/{total}** \u0441\u043b\u043e\u0442\u043e\u0432 \u2022 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e **{free}**",
    },
    "slots.running": {"en": "Running", "ru": "\u0417\u0430\u043f\u0443\u0449\u0435\u043d\u043e"},
    "slots.stopped": {"en": "Stopped", "ru": "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e"},
    "slots.free": {"en": "Free", "ru": "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u043e"},
    "slots.full_title": {
        "en": "No free slots",
        "ru": "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0445 \u0441\u043b\u043e\u0442\u043e\u0432 \u043d\u0435\u0442",
    },
    "slots.full": {
        "en": (
            "All **{total}** slots are busy right now, so new servers cannot be "
            "created. Try `{prefix}deploy` again later - a slot frees up as soon "
            "as someone deletes their VPS."
        ),
        "ru": (
            "\u0412\u0441\u0435 **{total}** \u0441\u043b\u043e\u0442\u043e\u0432 \u0437\u0430\u043d\u044f\u0442\u044b, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u043d\u043e\u0432\u044b\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u044b \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u0435\u043b\u044c\u0437\u044f. "
            "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 `{prefix}deploy` \u043f\u043e\u0437\u0436\u0435 \u2014 \u0441\u043b\u043e\u0442 \u043e\u0441\u0432\u043e\u0431\u043e\u0434\u0438\u0442\u0441\u044f, \u043a\u0430\u043a \u0442\u043e\u043b\u044c\u043a\u043e \u043a\u0442\u043e-\u0442\u043e \u0443\u0434\u0430\u043b\u0438\u0442 \u0441\u0432\u043e\u0439 VPS."
        ),
    },
    "slots.changed_title": {
        "en": "Slots updated",
        "ru": "\u0421\u043b\u043e\u0442\u044b \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u044b",
    },
    "slots.changed": {
        "en": "Capacity changed: **{old} \u2192 {new}** slots (in use: **{used}**).",
        "ru": "\u041b\u0438\u043c\u0438\u0442 \u0438\u0437\u043c\u0435\u043d\u0451\u043d: **{old} \u2192 {new}** \u0441\u043b\u043e\u0442\u043e\u0432 (\u0437\u0430\u043d\u044f\u0442\u043e: **{used}**).",
    },
    "slots.below_used": {
        "en": (
            "Heads up: **{used}** servers already exist, so the limit is now "
            "lower than the number of running VPS. Nothing was deleted - new "
            "deployments are simply blocked."
        ),
        "ru": (
            "\u0412\u043d\u0438\u043c\u0430\u043d\u0438\u0435: \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u0443\u0436\u0435 **{used}**, \u0442\u0430\u043a \u0447\u0442\u043e \u043b\u0438\u043c\u0438\u0442 \u043d\u0438\u0436\u0435 \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u0447\u0438\u0441\u043b\u0430 VPS. "
            "\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043e \u2014 \u043f\u0440\u043e\u0441\u0442\u043e \u043d\u0435\u043b\u044c\u0437\u044f \u0441\u043e\u0437\u0434\u0430\u0432\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0435."
        ),
    },
    "slots.usage": {
        "en": (
            "Usage: `{prefix}slots` \u2022 `{prefix}slots +1` \u2022 `{prefix}slots -1` "
            "\u2022 `{prefix}slots set 10`"
        ),
        "ru": (
            "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}slots` \u2022 `{prefix}slots +1` \u2022 `{prefix}slots -1` "
            "\u2022 `{prefix}slots set 10`"
        ),
    },
    "slots.limit": {
        "en": "Slots must be between **{min}** and **{max}**.",
        "ru": "\u0421\u043b\u043e\u0442\u043e\u0432 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043e\u0442 **{min}** \u0434\u043e **{max}**.",
    },
    # ---- staff: delete somebody else's VPS ----
    "wipe.title": {
        "en": "VPS deleted",
        "ru": "VPS \u0443\u0434\u0430\u043b\u0451\u043d",
    },
    "wipe.done": {
        "en": "The VPS of <@{user}> was deleted. Free slots now: **{free}/{total}**.",
        "ru": "VPS \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f <@{user}> \u0443\u0434\u0430\u043b\u0451\u043d. \u0421\u0432\u043e\u0431\u043e\u0434\u043d\u043e \u0441\u043b\u043e\u0442\u043e\u0432: **{free}/{total}**.",
    },
    "wipe.none": {
        "en": "<@{user}> does not have a VPS.",
        "ru": "\u0423 <@{user}> \u043d\u0435\u0442 VPS.",
    },
    "wipe.usage": {
        "en": "Usage: `{prefix}wipe @user` or `{prefix}wipe <user id>`",
        "ru": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}wipe @\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c` \u0438\u043b\u0438 `{prefix}wipe <id>`",
    },
    "wipe.notice_title": {
        "en": "Your VPS was deleted by staff",
        "ru": "\u0412\u0430\u0448 VPS \u0443\u0434\u0430\u043b\u0451\u043d \u0430\u0434\u043c\u0438\u043d\u043e\u043c",
    },
    "wipe.notice": {
        "en": (
            "A staff member deleted your VPS.\n**Reason:** {reason}\n\n"
            "You can create a new one with `{prefix}deploy` when a slot is free."
        ),
        "ru": (
            "\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 \u0443\u0434\u0430\u043b\u0438\u043b \u0432\u0430\u0448 VPS.\n**\u041f\u0440\u0438\u0447\u0438\u043d\u0430:** {reason}\n\n"
            "\u041a\u043e\u0433\u0434\u0430 \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0439 \u0441\u043b\u043e\u0442, \u043c\u043e\u0436\u043d\u043e \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439 \u0447\u0435\u0440\u0435\u0437 `{prefix}deploy`."
        ),
    },
    "wipe.no_reason": {
        "en": "not specified",
        "ru": "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u0430",
    },
}

RULES_I18N: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("One free server per person", "Alt accounts to farm extra servers are not allowed. Duplicates get removed."),
        ("No attacks or abuse", "No DDoS, port scanning, brute force, spam, phishing or proxy/VPN services."),
        ("No crypto mining or resource farming", "Miners, stress tests and 100% CPU loops are killed and the account is banned."),
        ("No illegal content", "Nothing pirated, stolen, malicious, or against Discord's Terms of Service."),
        ("Free tier is best effort", "Servers may be restarted, wiped or removed at any time. Keep your own backups."),
    ],
    "ru": [
        ("\u041e\u0434\u0438\u043d \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0430 \u0447\u0435\u043b\u043e\u0432\u0435\u043a\u0430", "\u0410\u043b\u044c\u0442-\u0430\u043a\u043a\u0430\u0443\u043d\u0442\u044b \u0434\u043b\u044f \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u0437\u0430\u043f\u0440\u0435\u0449\u0435\u043d\u044b. \u0414\u0443\u0431\u043b\u0438\u043a\u0430\u0442\u044b \u0443\u0434\u0430\u043b\u044f\u044e\u0442\u0441\u044f."),
        ("\u041d\u0438\u043a\u0430\u043a\u0438\u0445 \u0430\u0442\u0430\u043a \u0438 \u0437\u043b\u043e\u0443\u043f\u043e\u0442\u0440\u0435\u0431\u043b\u0435\u043d\u0438\u0439", "\u0417\u0430\u043f\u0440\u0435\u0449\u0435\u043d\u044b DDoS, \u0441\u043a\u0430\u043d \u043f\u043e\u0440\u0442\u043e\u0432, \u0431\u0440\u0443\u0442\u0444\u043e\u0440\u0441, \u0441\u043f\u0430\u043c, \u0444\u0438\u0448\u0438\u043d\u0433, \u043f\u0440\u043e\u043a\u0441\u0438 \u0438 VPN-\u0441\u0435\u0440\u0432\u0438\u0441\u044b."),
        ("\u041d\u0438\u043a\u0430\u043a\u043e\u0433\u043e \u043c\u0430\u0439\u043d\u0438\u043d\u0433\u0430 \u0438 \u0444\u0430\u0440\u043c\u0430 \u0440\u0435\u0441\u0443\u0440\u0441\u043e\u0432", "\u041c\u0430\u0439\u043d\u0435\u0440\u044b, \u0441\u0442\u0440\u0435\u0441\u0441-\u0442\u0435\u0441\u0442\u044b \u0438 \u0446\u0438\u043a\u043b\u044b \u043d\u0430 100% CPU \u0443\u0431\u0438\u0432\u0430\u044e\u0442\u0441\u044f, \u0430\u043a\u043a\u0430\u0443\u043d\u0442 \u0431\u0430\u043d\u0438\u0442\u0441\u044f."),
        ("\u041d\u0438\u043a\u0430\u043a\u043e\u0433\u043e \u043d\u0435\u0437\u0430\u043a\u043e\u043d\u043d\u043e\u0433\u043e \u043a\u043e\u043d\u0442\u0435\u043d\u0442\u0430", "\u041d\u0438\u043a\u0430\u043a\u043e\u0433\u043e \u043f\u0438\u0440\u0430\u0442\u0441\u0442\u0432\u0430, \u043a\u0440\u0430\u0436\u0438, \u0432\u0440\u0435\u0434\u043e\u043d\u043e\u0441\u043d\u043e\u0433\u043e \u041f\u041e \u0438 \u043d\u0430\u0440\u0443\u0448\u0435\u043d\u0438\u0439 \u043f\u0440\u0430\u0432\u0438\u043b Discord."),
        ("\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 \u0442\u0430\u0440\u0438\u0444 \u2014 \u0431\u0435\u0437 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u0439", "\u0421\u0435\u0440\u0432\u0435\u0440\u044b \u043c\u043e\u0433\u0443\u0442 \u0431\u044b\u0442\u044c \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0449\u0435\u043d\u044b, \u043e\u0447\u0438\u0449\u0435\u043d\u044b \u0438\u043b\u0438 \u0443\u0434\u0430\u043b\u0435\u043d\u044b \u0432 \u043b\u044e\u0431\u043e\u0439 \u043c\u043e\u043c\u0435\u043d\u0442. \u0414\u0435\u043b\u0430\u0439\u0442\u0435 \u0431\u044d\u043a\u0430\u043f\u044b."),
    ],
}


def t(lang: str | None, key: str, **kwargs) -> str:
    """Translate `key` into `lang`, falling back to English then to the key."""
    lang = normalize(lang)
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def rules(lang: str | None) -> list[tuple[str, str]]:
    return RULES_I18N.get(normalize(lang), RULES_I18N["en"])[:5]


def lang_label(lang: str | None) -> str:
    lang = normalize(lang)
    meta = LANGUAGES[lang]
    return f"{meta['flag']} {meta['name']}"
