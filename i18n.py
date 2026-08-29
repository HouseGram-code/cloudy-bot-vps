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
    "deploy.access_value": {"en": "**Web terminal**\n`sent to your DMs`", "ru": "**Веб-терминал**\n`прислан в ЛС`"},
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
    "stage.tmate": {"en": "Opening the web terminal…", "ru": "Открываем веб-терминал…"},
    "stage.health": {"en": "Running final health checks\u2026", "ru": "\u0424\u0438\u043d\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0441\u0435\u0440\u0432\u0438\u0441\u043e\u0432\u2026"},
    "success.title": {"en": "VPS deployed successfully!", "ru": "VPS \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u0441\u043e\u0437\u0434\u0430\u043d!"},
    "success.desc": {
        "en": "Your free VPS is **online** and ready to use.\nManage it any time with `{prefix}manage`.",
        "ru": "\u0412\u0430\u0448 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS **\u0432 \u0441\u0435\u0442\u0438** \u0438 \u0433\u043e\u0442\u043e\u0432 \u043a \u0440\u0430\u0431\u043e\u0442\u0435.\n\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u2014 \u043a\u043e\u043c\u0430\u043d\u0434\u0430 `{prefix}manage`.",
    },
    "success.access_field": {"en": "Access", "ru": "\u0414\u043e\u0441\u0442\u0443\u043f"},

    "ssh.system": {"en": "System", "ru": "\u0421\u0438\u0441\u0442\u0435\u043c\u0430"},
    "ssh.dm_failed_title": {"en": "I cannot DM you", "ru": "\u041d\u0435 \u043c\u043e\u0433\u0443 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c \u0432\u0430\u043c \u0432 \u041b\u0421"},
    "ssh.dm_failed_desc": {"en": "Your access link is only ever sent privately, but your DMs are closed.\n\n**Fix it:** Server settings → *Privacy Settings* → enable **Direct Messages**, then press **Web terminal** again.", "ru": "Ссылка доступа отправляется только лично, но ваши ЛС закрыты.\n\n**Как исправить:** Настройки сервера → *Конфиденциальность* → включите **Личные сообщения**, затем нажмите **Веб-терминал** снова."},

    "manage.title": {"en": "VPS Control Panel", "ru": "\u041f\u0430\u043d\u0435\u043b\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f VPS"},
    "manage.desc": {
        "en": "**{name}** \u2022 {status}\nUse the buttons below to control your server.",
        "ru": "**{name}** \u2022 {status}\n\u041a\u043d\u043e\u043f\u043a\u0438 \u043d\u0438\u0436\u0435 \u0443\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c.",
    },
    "manage.memory": {"en": "Memory", "ru": "\u041f\u0430\u043c\u044f\u0442\u044c"},
    "manage.allocated_offline": {"en": "**{value}** allocated \u2022 `server offline`", "ru": "\u0432\u044b\u0434\u0435\u043b\u0435\u043d\u043e **{value}** \u2022 `\u0441\u0435\u0440\u0432\u0435\u0440 \u043e\u0442\u043a\u043b\u044e\u0447\u0451\u043d`"},
    "manage.web_running": {"en": "Press **Web terminal** \u2014 the link is sent to your **DMs** only.", "ru": "Нажмите **Веб-терминал** — ссылка придёт только в **ЛС**."},
    "manage.web_stopped": {"en": "Start the server first, then press **Web terminal**.", "ru": "Сначала запустите сервер, затем нажмите **Веб-терминал**."},
    "manage.now_status": {"en": "Your VPS `{name}` is now **{status}**.", "ru": "\u0412\u0430\u0448 VPS `{name}` \u0442\u0435\u043f\u0435\u0440\u044c **{status}**."},
    "manage.session_closed": {"en": "\nThe old terminal session was closed — press **Web terminal** for a new one.", "ru": "\nСтарая сессия закрыта — нажмите **Веб-терминал** для новой."},
    "manage.started": {"en": "Server started", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u0437\u0430\u043f\u0443\u0449\u0435\u043d"},
    "manage.stopped": {"en": "Server stopped", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d"},
    "manage.restarted": {"en": "Server restarted", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0449\u0435\u043d"},
    "manage.already_own": {"en": "You already own a VPS \u2014 here is your control panel.", "ru": "\u0423 \u0432\u0430\u0441 \u0443\u0436\u0435 \u0435\u0441\u0442\u044c VPS \u2014 \u0432\u043e\u0442 \u043f\u0430\u043d\u0435\u043b\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f."},

    "btn.start": {"en": "Start", "ru": "\u0421\u0442\u0430\u0440\u0442"},
    "btn.stop": {"en": "Stop", "ru": "\u0421\u0442\u043e\u043f"},
    "btn.restart": {"en": "Restart", "ru": "\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a"},
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
    "help.manage": {"en": "Live server info + Start / Stop / Restart / Web terminal buttons.", "ru": "Статистика сервера и кнопки Старт / Стоп / Перезапуск / Веб-терминал."},
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
    # ---------------- profile / leaf economy ----------------
    "profile.title": {"en": "Profile", "ru": "\u041f\u0440\u043e\u0444\u0438\u043b\u044c"},
    "profile.desc": {
        "en": "Your account, your leaves and your free VPS \u2014 all in one card.",
        "ru": "\u0412\u0430\u0448 \u0430\u043a\u043a\u0430\u0443\u043d\u0442, \u043b\u0438\u0441\u0442\u0438\u043a\u0438 \u0438 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS \u2014 \u0432\u0441\u0451 \u0432 \u043e\u0434\u043d\u043e\u0439 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0435.",
    },
    "profile.name": {"en": "Name", "ru": "\u0418\u043c\u044f"},
    "profile.id": {"en": "ID", "ru": "\u0410\u0439\u0434\u0438"},
    "profile.balance": {"en": "Leaves", "ru": "\u041b\u0438\u0441\u0442\u0438\u043a\u0438"},
    "profile.balance_value": {
        "en": "**{leaves}** \U0001F343 \u2022 `-{cost}/h` while the VPS runs",
        "ru": "**{leaves}** \U0001F343 \u2022 `-{cost}/\u0447\u0430\u0441` \u043f\u043e\u043a\u0430 VPS \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442",
    },
    "profile.runtime": {"en": "Uptime left", "ru": "\u0425\u0432\u0430\u0442\u0438\u0442 \u043d\u0430"},
    "profile.runtime_value": {
        "en": "\u2248 **{hours} h** of VPS uptime",
        "ru": "\u2248 **{hours} \u0447** \u0440\u0430\u0431\u043e\u0442\u044b VPS",
    },
    "profile.runtime_empty": {
        "en": "No leaves left \u2014 claim the bonus to keep the VPS alive.",
        "ru": "\u041b\u0438\u0441\u0442\u0438\u043a\u043e\u0432 \u043d\u0435\u0442 \u2014 \u0437\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u0431\u043e\u043d\u0443\u0441, \u0447\u0442\u043e\u0431\u044b VPS \u0440\u0430\u0431\u043e\u0442\u0430\u043b.",
    },
    "profile.vps": {"en": "Your VPS", "ru": "\u0412\u0430\u0448 VPS"},
    "profile.vps_yes": {
        "en": "`{name}` \u2022 {status}",
        "ru": "`{name}` \u2022 {status}",
    },
    "profile.vps_none": {
        "en": "You have none yet \u2014 `{prefix}deploy` gives you a free one.",
        "ru": "\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u2014 `{prefix}deploy` \u0432\u044b\u0434\u0430\u0441\u0442 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439.",
    },
    "profile.bonus": {"en": "Daily bonus", "ru": "\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 \u0431\u043e\u043d\u0443\u0441"},
    "profile.bonus_ready": {
        "en": "**Ready!** Press the button below for **+{amount}** \U0001F343",
        "ru": "**\u0414\u043e\u0441\u0442\u0443\u043f\u0435\u043d!** \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u043d\u0438\u0436\u0435 \u0438 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 **+{amount}** \U0001F343",
    },
    "profile.bonus_wait": {
        "en": "Claimed \u2022 next **+{amount}** \U0001F343 <t:{ts}:R>",
        "ru": "\u0423\u0436\u0435 \u0432\u0437\u044f\u0442 \u2022 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0435 **+{amount}** \U0001F343 <t:{ts}:R>",
    },
    "profile.stats": {"en": "Stats", "ru": "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430"},
    "profile.stats_value": {
        "en": "Earned **{earned}** \u2022 spent **{spent}** \u2022 bonuses **{bonuses}**",
        "ru": "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u043e **{earned}** \u2022 \u043f\u043e\u0442\u0440\u0430\u0447\u0435\u043d\u043e **{spent}** \u2022 \u0431\u043e\u043d\u0443\u0441\u043e\u0432 **{bonuses}**",
    },
    "profile.economy": {"en": "How leaves work", "ru": "\u041a\u0430\u043a \u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0442 \u043b\u0438\u0441\u0442\u0438\u043a\u0438"},
    "profile.economy_value": {
        "en": (
            "\u2022 new accounts start with **{start}** \U0001F343\n"
            "\u2022 a running VPS costs **{cost}** \U0001F343 per hour\n"
            "\u2022 `{prefix}bonus` gives **+{amount}** \U0001F343 once every {hours} h\n"
            "\u2022 at **0** \U0001F343 the VPS is only stopped, never deleted"
        ),
        "ru": (
            "\u2022 \u043d\u043e\u0432\u044b\u043c \u0432\u044b\u0434\u0430\u0451\u0442\u0441\u044f **{start}** \U0001F343\n"
            "\u2022 \u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0449\u0438\u0439 VPS \u0441\u0442\u043e\u0438\u0442 **{cost}** \U0001F343 \u0432 \u0447\u0430\u0441\n"
            "\u2022 `{prefix}bonus` \u0434\u0430\u0451\u0442 **+{amount}** \U0001F343 \u0440\u0430\u0437 \u0432 {hours} \u0447\n"
            "\u2022 \u043d\u0430 **0** \U0001F343 VPS \u0442\u043e\u043b\u044c\u043a\u043e \u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u0435\u0442\u0441\u044f, \u043d\u043e \u043d\u0435 \u0443\u0434\u0430\u043b\u044f\u0435\u0442\u0441\u044f"
        ),
    },
    "btn.bonus": {"en": "Daily bonus", "ru": "\u0411\u043e\u043d\u0443\u0441"},
    "btn.bonus_wait": {"en": "Bonus taken", "ru": "\u0411\u043e\u043d\u0443\u0441 \u0432\u0437\u044f\u0442"},
    "btn.profile_refresh": {"en": "Refresh", "ru": "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c"},
    "bonus.ok_title": {
        "en": "Daily bonus claimed",
        "ru": "\u0411\u043e\u043d\u0443\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d",
    },
    "bonus.ok": {
        "en": "**+{amount}** \U0001F343 added \u2014 your balance is now **{balance}** \U0001F343 (\u2248 {hours} h of uptime).\nCome back <t:{ts}:R> for the next one.",
        "ru": "**+{amount}** \U0001F343 \u043d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e \u2014 \u0431\u0430\u043b\u0430\u043d\u0441 \u0442\u0435\u043f\u0435\u0440\u044c **{balance}** \U0001F343 (\u2248 {hours} \u0447 \u0440\u0430\u0431\u043e\u0442\u044b).\n\u0417\u0430\u0445\u043e\u0434\u0438\u0442\u0435 \u0441\u043d\u043e\u0432\u0430 <t:{ts}:R>.",
    },
    "bonus.wait_title": {
        "en": "Bonus already claimed",
        "ru": "\u0411\u043e\u043d\u0443\u0441 \u0443\u0436\u0435 \u0432\u0437\u044f\u0442",
    },
    "bonus.wait": {
        "en": "The daily bonus is available once every {hours} h.\nNext **+{amount}** \U0001F343 <t:{ts}:R>.",
        "ru": "\u0411\u043e\u043d\u0443\u0441 \u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0440\u0430\u0437 \u0432 {hours} \u0447.\n\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0435 **+{amount}** \U0001F343 <t:{ts}:R>.",
    },
    "grant.title": {"en": "Leaves updated", "ru": "\u0411\u0430\u043b\u0430\u043d\u0441 \u0438\u0437\u043c\u0435\u043d\u0451\u043d"},
    "grant.given": {
        "en": "Gave **+{amount}** \U0001F343 to <@{user}>.\nNew balance: **{balance}** \U0001F343",
        "ru": "\u0412\u044b\u0434\u0430\u043d\u043e **+{amount}** \U0001F343 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e <@{user}>.\n\u041d\u043e\u0432\u044b\u0439 \u0431\u0430\u043b\u0430\u043d\u0441: **{balance}** \U0001F343",
    },
    "grant.taken": {
        "en": "Removed **{amount}** \U0001F343 from <@{user}>.\nNew balance: **{balance}** \U0001F343",
        "ru": "\u0421\u043f\u0438\u0441\u0430\u043d\u043e **{amount}** \U0001F343 \u0443 <@{user}>.\n\u041d\u043e\u0432\u044b\u0439 \u0431\u0430\u043b\u0430\u043d\u0441: **{balance}** \U0001F343",
    },
    "grant.usage": {
        "en": "Usage: `{prefix}give <@user|id> <amount>` \u2014 for example `{prefix}give @user 25`. A negative amount takes leaves away.",
        "ru": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}give <@\u044e\u0437\u0435\u0440|id> <\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e>` \u2014 \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 `{prefix}give @user 25`. \u041e\u0442\u0440\u0438\u0446\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u0447\u0438\u0441\u043b\u043e \u0441\u043f\u0438\u0441\u044b\u0432\u0430\u0435\u0442.",
    },
    "grant.bad_amount": {
        "en": "The amount must be a whole number between -{max} and {max}.",
        "ru": "\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u0446\u0435\u043b\u044b\u043c \u0447\u0438\u0441\u043b\u043e\u043c \u043e\u0442 -{max} \u0434\u043e {max}.",
    },
    "grant.notice_title": {
        "en": "You received leaves",
        "ru": "\u0412\u0430\u043c \u043d\u0430\u0447\u0438\u0441\u043b\u0438\u043b\u0438 \u043b\u0438\u0441\u0442\u0438\u043a\u0438",
    },
    "grant.notice": {
        "en": "Staff added **+{amount}** \U0001F343 to your account.\nBalance: **{balance}** \U0001F343 (\u2248 {hours} h of VPS uptime).",
        "ru": "\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f \u043d\u0430\u0447\u0438\u0441\u043b\u0438\u043b\u0430 \u0432\u0430\u043c **+{amount}** \U0001F343.\n\u0411\u0430\u043b\u0430\u043d\u0441: **{balance}** \U0001F343 (\u2248 {hours} \u0447 \u0440\u0430\u0431\u043e\u0442\u044b VPS).",
    },
    "leaves.low_title": {
        "en": "Not enough leaves",
        "ru": "\u041d\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442 \u043b\u0438\u0441\u0442\u0438\u043a\u043e\u0432",
    },
    "leaves.low": {
        "en": "A VPS costs **{cost}** \U0001F343 per hour and you have **{balance}** \U0001F343.\nGrab the daily bonus with `{prefix}bonus` (**+{amount}** \U0001F343) and try again.",
        "ru": "VPS \u0441\u0442\u043e\u0438\u0442 **{cost}** \U0001F343 \u0432 \u0447\u0430\u0441, \u0430 \u0443 \u0432\u0430\u0441 **{balance}** \U0001F343.\n\u0417\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u0431\u043e\u043d\u0443\u0441 \u0447\u0435\u0440\u0435\u0437 `{prefix}bonus` (**+{amount}** \U0001F343) \u0438 \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.",
    },
    "billing.title": {
        "en": "VPS stopped \u2014 out of leaves",
        "ru": "VPS \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d \u2014 \u0437\u0430\u043a\u043e\u043d\u0447\u0438\u043b\u0438\u0441\u044c \u043b\u0438\u0441\u0442\u0438\u043a\u0438",
    },
    "billing.desc": {
        "en": "Your VPS `{name}` was stopped because your balance reached **0** \U0001F343.\n**Nothing is deleted** \u2014 all your files are still there.\n\nTake the daily bonus with `{prefix}bonus` (**+{amount}** \U0001F343) and start the server again from `{prefix}manage`.",
        "ru": "\u0412\u0430\u0448 VPS `{name}` \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d: \u0431\u0430\u043b\u0430\u043d\u0441 \u0434\u043e\u0448\u0451\u043b \u0434\u043e **0** \U0001F343.\n**\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043e** \u2014 \u0432\u0441\u0435 \u0444\u0430\u0439\u043b\u044b \u043d\u0430 \u043c\u0435\u0441\u0442\u0435.\n\n\u0417\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u0431\u043e\u043d\u0443\u0441 \u0447\u0435\u0440\u0435\u0437 `{prefix}bonus` (**+{amount}** \U0001F343) \u0438 \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440 \u0441\u043d\u043e\u0432\u0430 \u0447\u0435\u0440\u0435\u0437 `{prefix}manage`.",
    },
    "admin.leaves": {"en": "Leaf economy", "ru": "\u041b\u0438\u0441\u0442\u0438\u043a\u0438"},
    "admin.leaves_value": {
        "en": "start **{start}** \u2022 **{cost}**/h \u2022 bonus **+{amount}** / {hours} h",
        "ru": "\u0441\u0442\u0430\u0440\u0442 **{start}** \u2022 **{cost}**/\u0447\u0430\u0441 \u2022 \u0431\u043e\u043d\u0443\u0441 **+{amount}** / {hours} \u0447",
    },
    "admin.btn_give": {"en": "Give leaves", "ru": "\u0412\u044b\u0434\u0430\u0442\u044c \u043b\u0438\u0441\u0442\u0438\u043a\u0438"},
    "admin.give_modal": {
        "en": "Give leaves to a user",
        "ru": "\u0412\u044b\u0434\u0430\u0447\u0430 \u043b\u0438\u0441\u0442\u0438\u043a\u043e\u0432",
    },
    "admin.give_user": {
        "en": "User ID or mention",
        "ru": "ID \u0438\u043b\u0438 \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435",
    },
    "admin.give_amount": {
        "en": "Amount of leaves (can be negative)",
        "ru": "\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u043b\u0438\u0441\u0442\u0438\u043a\u043e\u0432 (\u043c\u043e\u0436\u043d\u043e \u043c\u0438\u043d\u0443\u0441)",
    },
    "admin.give_bad_user": {
        "en": "Could not read that user. Use a numeric ID or a mention.",
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043d\u044f\u0442\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f. \u0423\u043a\u0430\u0436\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e\u0432\u043e\u0439 ID \u0438\u043b\u0438 \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435.",
    },
    "help.profile": {
        "en": "Your profile: name, ID, leaf balance and the daily bonus button.",
        "ru": "\u0412\u0430\u0448 \u043f\u0440\u043e\u0444\u0438\u043b\u044c: \u0438\u043c\u044f, \u0430\u0439\u0434\u0438, \u0431\u0430\u043b\u0430\u043d\u0441 \u043b\u0438\u0441\u0442\u0438\u043a\u043e\u0432 \u0438 \u043a\u043d\u043e\u043f\u043a\u0430 \u0431\u043e\u043d\u0443\u0441\u0430.",
    },
    "help.bonus": {
        "en": "Claim **+{amount}** \U0001F343 once every {hours} hours.",
        "ru": "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c **+{amount}** \U0001F343 \u0440\u0430\u0437 \u0432 {hours} \u0447\u0430\u0441\u043e\u0432.",
    },
    # ---------------- resource plan (RAM / disk / vCPU) ----------------
    "plan.title": {"en": "Free VPS resources", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e\u0433\u043e VPS"},
    "plan.desc": {"en": "What every new free VPS gets. Staff can change it live with the buttons in `{prefix}admin` or with `{prefix}plan`.", "ru": "\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0440\u0435\u0441\u0443\u0440\u0441\u043e\u0432 \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442 \u043a\u0430\u0436\u0434\u044b\u0439 \u043d\u043e\u0432\u044b\u0439 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS. \u0410\u0434\u043c\u0438\u043d\u044b \u043c\u0435\u043d\u044f\u044e\u0442 \u044d\u0442\u043e \u043a\u043d\u043e\u043f\u043a\u0430\u043c\u0438 \u0432 `{prefix}admin` \u0438\u043b\u0438 \u043a\u043e\u043c\u0430\u043d\u0434\u043e\u0439 `{prefix}plan`."},
    "plan.ram": {"en": "Memory", "ru": "\u041e\u0417\u0423"},
    "plan.ram_value": {"en": "**{ram} MB**\n`+ {swap} MB swap`", "ru": "**{ram} \u041c\u0411**\n`+ {swap} \u041c\u0411 swap`"},
    "plan.cpu": {"en": "Processor", "ru": "\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440"},
    "plan.cpu_value": {"en": "**{cpu} vCPU**", "ru": "**{cpu} vCPU**"},
    "plan.disk": {"en": "Storage", "ru": "\u0414\u0438\u0441\u043a"},
    "plan.disk_value": {"en": "**{disk} GB**\n`SSD`", "ru": "**{disk} \u0413\u0411**\n`SSD`"},
    "plan.limits": {"en": "Limits", "ru": "\u0413\u0440\u0430\u043d\u0438\u0446\u044b"},
    "plan.limits_value": {"en": "RAM `{ram_min}-{ram_max} MB` \u2022 Disk `{disk_min}-{disk_max} GB` \u2022 CPU `{cpu_min}-{cpu_max}`", "ru": "\u041e\u0417\u0423 `{ram_min}-{ram_max} \u041c\u0411` \u2022 \u0434\u0438\u0441\u043a `{disk_min}-{disk_max} \u0413\u0411` \u2022 CPU `{cpu_min}-{cpu_max}`"},
    "plan.note": {"en": "Good to know", "ru": "\u0412\u0430\u0436\u043d\u043e"},
    "plan.note_value": {"en": "New limits apply to **newly created** servers. Existing VPS keep their current resources until they are recreated with `{prefix}destroy` + `{prefix}deploy`.", "ru": "\u041d\u043e\u0432\u044b\u0435 \u043b\u0438\u043c\u0438\u0442\u044b \u0434\u0435\u0439\u0441\u0442\u0432\u0443\u044e\u0442 \u0434\u043b\u044f **\u043d\u043e\u0432\u044b\u0445** \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432. \u0423\u0436\u0435 \u0441\u043e\u0437\u0434\u0430\u043d\u043d\u044b\u0435 VPS \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e\u0442 \u0441\u0432\u043e\u0438 \u0440\u0435\u0441\u0443\u0440\u0441\u044b, \u043f\u043e\u043a\u0430 \u0438\u0445 \u043d\u0435 \u043f\u0435\u0440\u0435\u0441\u043e\u0437\u0434\u0430\u0434\u0443\u0442 \u0447\u0435\u0440\u0435\u0437 `{prefix}destroy` + `{prefix}deploy`."},
    "plan.changed_title": {"en": "Resources updated", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u044b"},
    "plan.changed": {"en": "RAM: **{old_ram} \u2192 {ram} MB**\nCPU: **{old_cpu} \u2192 {cpu} vCPU**\nDisk: **{old_disk} \u2192 {disk} GB**", "ru": "\u041e\u0417\u0423: **{old_ram} \u2192 {ram} \u041c\u0411**\nCPU: **{old_cpu} \u2192 {cpu} vCPU**\n\u0414\u0438\u0441\u043a: **{old_disk} \u2192 {disk} \u0413\u0411**"},
    "plan.usage": {"en": "Usage: `{prefix}plan` \u2022 `{prefix}plan ram 2048` \u2022 `{prefix}plan disk 20` \u2022 `{prefix}plan cpu 2` \u2022 `{prefix}plan reset`", "ru": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: `{prefix}plan` \u2022 `{prefix}plan ram 2048` \u2022 `{prefix}plan disk 20` \u2022 `{prefix}plan cpu 2` \u2022 `{prefix}plan reset`"},
    "plan.bad_value": {"en": "Give a number, for example `{prefix}plan ram 2048`.", "ru": "\u0423\u043a\u0430\u0436\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 `{prefix}plan ram 2048`."},
    "plan.clamped": {"en": "The value was adjusted to fit the host limits.", "ru": "\u0417\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u043f\u043e\u0434\u043e\u0433\u043d\u0430\u043d\u043e \u043f\u043e\u0434 \u043b\u0438\u043c\u0438\u0442\u044b \u0445\u043e\u0441\u0442\u0430."},
    "plan.reset_title": {"en": "Resources reset", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b \u0441\u0431\u0440\u043e\u0448\u0435\u043d\u044b"},
    "plan.default": {"en": "default plan", "ru": "\u0442\u0430\u0440\u0438\u0444 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e"},
    "plan.custom": {"en": "custom plan", "ru": "\u0438\u0437\u043c\u0435\u043d\u0451\u043d \u0430\u0434\u043c\u0438\u043d\u043e\u043c"},
    "admin.resources": {"en": "Free VPS resources", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b VPS"},
    "admin.resources_value": {"en": "**{ram} MB** RAM \u2022 **{cpu} vCPU** \u2022 **{disk} GB** SSD \u2022 `{state}`", "ru": "**{ram} \u041c\u0411** \u041e\u0417\u0423 \u2022 **{cpu} vCPU** \u2022 **{disk} \u0413\u0411** SSD \u2022 `{state}`"},
    "admin.btn_ram_plus": {"en": "+512 MB RAM", "ru": "+512 \u041c\u0411 \u041e\u0417\u0423"},
    "admin.btn_ram_minus": {"en": "-512 MB RAM", "ru": "-512 \u041c\u0411 \u041e\u0417\u0423"},
    "admin.btn_disk_plus": {"en": "+5 GB disk", "ru": "+5 \u0413\u0411 \u0434\u0438\u0441\u043a"},
    "admin.btn_disk_minus": {"en": "-5 GB disk", "ru": "-5 \u0413\u0411 \u0434\u0438\u0441\u043a"},
    "admin.btn_plan": {"en": "Resources", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b"},
    "help.plan": {"en": "Show / change the resources of the free plan.", "ru": "\u041f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u0438\u043b\u0438 \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0440\u0435\u0441\u0443\u0440\u0441\u044b \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e\u0433\u043e \u0442\u0430\u0440\u0438\u0444\u0430."},
    "manage.resources": {"en": "Resources", "ru": "\u0420\u0435\u0441\u0443\u0440\u0441\u044b"},
    "manage.details": {"en": "Details", "ru": "\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438"},
    "manage.offline_hint": {"en": "The server is off \u2014 press **Start** to boot it up.", "ru": "\u0421\u0435\u0440\u0432\u0435\u0440 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d \u2014 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 **\u0421\u0442\u0430\u0440\u0442**, \u0447\u0442\u043e\u0431\u044b \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c."},
    "vps.limit_title": {"en": "VPS limit reached", "ru": "\u0414\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442 \u043b\u0438\u043c\u0438\u0442 VPS"},
    "vps.limit": {"en": "Your account can run **{limit}** VPS and you already have **{used}**.\nUse `{prefix}manage` to control it, or `{prefix}destroy` to delete it first.", "ru": "\u041d\u0430 \u043e\u0434\u0438\u043d \u0430\u043a\u043a\u0430\u0443\u043d\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e **{limit}** VPS, \u0430 \u0443 \u0432\u0430\u0441 \u0443\u0436\u0435 **{used}**.\n\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 `{prefix}manage` \u0434\u043b\u044f \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u0438\u043b\u0438 `{prefix}destroy`, \u0447\u0442\u043e\u0431\u044b \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0442\u0435\u043a\u0443\u0449\u0438\u0439."},
    # ---------------- sshx: browser terminal ----------------
    "sshx.dm_title": {"en": "Your VPS \u2014 web terminal (sshx)", "ru": "\u0412\u0430\u0448 VPS \u2014 \u0432\u0435\u0431-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b (sshx)"},
    "sshx.dm_desc": {"en": "`{name}` \u2022 ID `{sid}`\n\nOpen this link in any browser \u2014 no SSH client, no keys, no open ports.", "ru": "`{name}` \u2022 ID `{sid}`\n\n\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u0432 \u043b\u044e\u0431\u043e\u043c \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u2014 \u0431\u0435\u0437 SSH-\u043a\u043b\u0438\u0435\u043d\u0442\u0430, \u043a\u043b\u044e\u0447\u0435\u0439 \u0438 \u043f\u043e\u0440\u0442\u043e\u0432."},
    "sshx.link": {"en": "Link", "ru": "\u0421\u0441\u044b\u043b\u043a\u0430"},
    "sshx.how": {"en": "How it works", "ru": "\u041a\u0430\u043a \u044d\u0442\u043e \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442"},
    "sshx.how_value": {"en": "Everything after `#` is the encryption key: it stays in your browser and never reaches the server. The session lives as long as the VPS runs.", "ru": "\u0412\u0441\u0451 \u043f\u043e\u0441\u043b\u0435 `#` \u2014 \u044d\u0442\u043e \u043a\u043b\u044e\u0447 \u0448\u0438\u0444\u0440\u043e\u0432\u0430\u043d\u0438\u044f: \u043e\u043d \u043e\u0441\u0442\u0430\u0451\u0442\u0441\u044f \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u0438 \u043d\u0435 \u043f\u043e\u043f\u0430\u0434\u0430\u0435\u0442 \u043d\u0430 \u0441\u0435\u0440\u0432\u0435\u0440. \u0421\u0435\u0441\u0441\u0438\u044f \u0436\u0438\u0432\u0451\u0442, \u043f\u043e\u043a\u0430 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 VPS."},
    "sshx.keep_private": {"en": "Do not share the link", "ru": "\u041d\u0435 \u0434\u0435\u043b\u0438\u0442\u0435\u0441\u044c \u0441\u0441\u044b\u043b\u043a\u043e\u0439"},
    "sshx.keep_private_value": {"en": "Anyone who opens it gets a root shell in your VPS. Run `{prefix}sshx` again to kill the old session and get a fresh link.", "ru": "\u041a\u0442\u043e \u043e\u0442\u043a\u0440\u043e\u0435\u0442 \u0441\u0441\u044b\u043b\u043a\u0443 \u2014 \u043f\u043e\u043b\u0443\u0447\u0438\u0442 root \u0432 \u0432\u0430\u0448\u0435\u043c VPS. \u041a\u043e\u043c\u0430\u043d\u0434\u0430 `{prefix}sshx` \u0437\u0430\u043a\u0440\u043e\u0435\u0442 \u0441\u0442\u0430\u0440\u0443\u044e \u0441\u0435\u0441\u0441\u0438\u044e \u0438 \u0432\u044b\u0434\u0430\u0441\u0442 \u043d\u043e\u0432\u0443\u044e \u0441\u0441\u044b\u043b\u043a\u0443."},
    "sshx.timeout": {"en": "sshx did not answer in time. Try again.", "ru": "sshx \u043d\u0435 \u043e\u0442\u0432\u0435\u0442\u0438\u043b \u0432\u043e\u0432\u0440\u0435\u043c\u044f. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430."},
    "sshx.not_running": {"en": "Start the VPS first \u2014 a stopped server cannot open a web terminal. Use `{prefix}manage`.", "ru": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 VPS \u2014 \u043d\u0430 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u043e\u043c \u0441\u0435\u0440\u0432\u0435\u0440\u0435 \u0432\u0435\u0431-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b \u043d\u0435 \u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 `{prefix}manage`."},
    "sshx.no_vps": {"en": "You do not have a VPS yet. Use `{prefix}deploy` to create one.", "ru": "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 VPS. \u0421\u043e\u0437\u0434\u0430\u0439\u0442\u0435 \u0435\u0433\u043e \u043a\u043e\u043c\u0430\u043d\u0434\u043e\u0439 `{prefix}deploy`."},
    "sshx.disabled": {"en": "The web terminal is turned off on this host (`SSHX_ENABLED=0`).", "ru": "\u0412\u0435\u0431-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b \u043e\u0442\u043a\u043b\u044e\u0447\u0451\u043d \u043d\u0430 \u044d\u0442\u043e\u043c \u0441\u0435\u0440\u0432\u0435\u0440\u0435 (`SSHX_ENABLED=0`)."},
    "sshx.install_failed": {"en": "Could not install the sshx client inside the VPS \u2014 the container needs outbound HTTPS to `sshx.io`.", "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043b\u0438\u0435\u043d\u0442 sshx \u0432\u043d\u0443\u0442\u0440\u0438 VPS \u2014 \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u0443 \u043d\u0443\u0436\u0435\u043d \u0438\u0441\u0445\u043e\u0434\u044f\u0449\u0438\u0439 HTTPS \u043a `sshx.io`."},
    "sshx.no_link": {"en": "sshx started but did not print a link.\n```\n{tail}\n```", "ru": "sshx \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u043b\u0441\u044f, \u043d\u043e \u043d\u0435 \u0432\u044b\u0434\u0430\u043b \u0441\u0441\u044b\u043b\u043a\u0443.\n```\n{tail}\n```"},
    "sshx.check_dms_title": {"en": "Link sent to your DMs", "ru": "\u0421\u0441\u044b\u043b\u043a\u0430 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430 \u0432 \u043b\u0438\u0447\u043d\u044b\u0435"},
    "sshx.check_dms_desc": {"en": "The web-terminal link is private \u2014 check your direct messages.", "ru": "\u0421\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0432\u0435\u0431-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b \u043f\u0440\u0438\u0432\u0430\u0442\u043d\u0430\u044f \u2014 \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043b\u0438\u0447\u043d\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f."},
    "sshx.sent_dm": {"en": "Sent to your **DMs** \u2014 check your private messages.", "ru": "Отправлено в **ЛС** — проверьте личные сообщения."},
    "sshx.sent_ephemeral": {"en": "Sent privately (DMs are closed, so it was shown only to you here).", "ru": "Отправлено приватно (ЛС закрыты — видно только вам)."},
    "sshx.slow": {"en": "The terminal is taking longer than usual. Press **Web terminal** in a moment.", "ru": "Терминал создаётся дольше обычного. Нажмите **Веб-терминал** через минуту."},
    "sshx.retry": {"en": "Could not open the terminal yet \u2014 press **Web terminal** to retry.\nDetails were sent to you privately.", "ru": "Пока не удалось открыть терминал — нажмите **Веб-терминал** ещё раз.\nПодробности отправлены лично."},
    "btn.sshx": {"en": "Web terminal", "ru": "\u0412\u0435\u0431-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b"},
    "help.sshx": {"en": "Open your VPS in a browser terminal (sshx.io) — no SSH client, no keys, no open ports.", "ru": "Открыть VPS в браузерном терминале (sshx.io) — без SSH-клиента, ключей и открытых портов."},
    "manage.web_hint": {"en": "No SSH client? `{prefix}sshx` opens the same VPS in your browser.", "ru": "\u041d\u0435\u0442 SSH-\u043a\u043b\u0438\u0435\u043d\u0442\u0430? `{prefix}sshx` \u043e\u0442\u043a\u0440\u043e\u0435\u0442 \u0442\u043e\u0442 \u0436\u0435 VPS \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435."},
    "about.title": {
        "en": "Free VPS hosting, right from Discord",
        "ru": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS \u043f\u0440\u044f\u043c\u043e \u0438\u0437 Discord",
    },
    "about.desc": {
        "en": (
            "**Cloudy VPS Bot** hands out free Ubuntu 22.04 servers in seconds.\n"
            "One command, one slot, full root access over SSH \u2014 no card, no cost."
        ),
        "ru": (
            "**Cloudy VPS Bot** \u0432\u044b\u0434\u0430\u0451\u0442 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u044b Ubuntu 22.04 \u0437\u0430 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0435\u043a\u0443\u043d\u0434.\n"
            "\u041e\u0434\u043d\u0430 \u043a\u043e\u043c\u0430\u043d\u0434\u0430, \u043e\u0434\u0438\u043d \u0441\u043b\u043e\u0442, \u043f\u043e\u043b\u043d\u044b\u0439 root \u043f\u043e SSH \u2014 \u0431\u0435\u0437 \u043a\u0430\u0440\u0442\u044b \u0438 \u043f\u043b\u0430\u0442\u044b."
        ),
    },
    "about.specs": {"en": "What you get", "ru": "\u0427\u0442\u043e \u0432\u044b \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442\u0435"},
    "about.start": {"en": "How to start", "ru": "\u041a\u0430\u043a \u043d\u0430\u0447\u0430\u0442\u044c"},
    "about.start_value": {
        "en": (
            "**1.** `{prefix}deploy` \u2014 pick the free plan and press Start\n"
            "**2.** the SSH line arrives in your DM\n"
            "**3.** `{prefix}manage` \u2014 restart, get SSH again or check status"
        ),
        "ru": (
            "**1.** `{prefix}deploy` \u2014 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 \u043f\u043b\u0430\u043d \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u0421\u0442\u0430\u0440\u0442\n"
            "**2.** SSH-\u0441\u0442\u0440\u043e\u043a\u0430 \u043f\u0440\u0438\u0434\u0451\u0442 \u0432\u0430\u043c \u0432 \u041b\u0421\n"
            "**3.** `{prefix}manage` \u2014 \u0440\u0435\u0441\u0442\u0430\u0440\u0442, \u043d\u043e\u0432\u044b\u0439 SSH \u0438\u043b\u0438 \u0441\u0442\u0430\u0442\u0443\u0441"
        ),
    },
    "about.links": {"en": "Useful commands", "ru": "\u041f\u043e\u043b\u0435\u0437\u043d\u044b\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b"},
    "about.links_value": {
        "en": (
            "`{prefix}slots` \u2022 `{prefix}rules` \u2022 `{prefix}help` \u2022 "
            "`{prefix}lang ru|en` \u2022 `{prefix}destroy`"
        ),
        "ru": (
            "`{prefix}slots` \u2022 `{prefix}rules` \u2022 `{prefix}help` \u2022 "
            "`{prefix}lang ru|en` \u2022 `{prefix}destroy`"
        ),
    },
    "help.about": {
        "en": "What this bot is and how the free VPS works.",
        "ru": "\u0427\u0442\u043e \u0443\u043c\u0435\u0435\u0442 \u0431\u043e\u0442 \u0438 \u043a\u0430\u043a \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 VPS.",
    },
    "slots.presence": {
        "en": "{used}/{total} slots \u2022 {running} online",
        "ru": "{used}/{total} \u0441\u043b\u043e\u0442\u043e\u0432 \u2022 {running} \u043e\u043d\u043b\u0430\u0439\u043d",
    },
    "slots.short": {
        "en": "**{used}/{total}** slots \u2022 {running} running \u2022 {stopped} stopped",
        "ru": "**{used}/{total}** \u0441\u043b\u043e\u0442\u043e\u0432 \u2022 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u043e {running} \u2022 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e {stopped}",
    },
    "help.slots": {
        "en": "Free slots, how many servers are running and how many are stopped.",
        "ru": "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0435 \u0441\u043b\u043e\u0442\u044b, \u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u043e \u0438 \u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e.",
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
