"""All Discord embeds / visual formatting for Cloudy VPS Bot.

Every builder takes an optional `lang` ("en" or "ru"); strings come from i18n.py.
"""

from __future__ import annotations

import datetime as dt

import discord

from config import (
    BOT_FOOTER,
    BOT_NAME,
    BOT_VERSION,
    COMMAND_PREFIX,
    COLOR_ERROR,
    COLOR_NEUTRAL,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    EMOJI,
    PLAN,
)
from i18n import DEFAULT_LANG, LANGUAGES, lang_label, rules as rules_for
from i18n import t

FILLED = "\u2588"
EMPTY = "\u2591"
P = COMMAND_PREFIX


def progress_bar(percent: int, width: int = 22) -> str:
    percent = max(0, min(100, int(percent)))
    filled = round(width * percent / 100)
    return f"`{FILLED * filled}{EMPTY * (width - filled)}` **{percent}%**"


def human_uptime(seconds: float) -> str:
    seconds = int(max(0, seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def status_badge(status: str, lang: str = DEFAULT_LANG) -> str:
    status = (status or "unknown").lower()
    if status == "running":
        return f"{EMOJI['online']} **{t(lang, 'generic.online')}**"
    if status in ("exited", "created", "dead"):
        return f"{EMOJI['offline']} **{t(lang, 'generic.offline')}**"
    return f"{EMOJI['pending']} **{status.capitalize()}**"


def _footer(embed: discord.Embed) -> discord.Embed:
    embed.set_footer(text=BOT_FOOTER)
    embed.timestamp = dt.datetime.now(dt.timezone.utc)
    return embed


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def rules_embed(lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['scroll']} {t(lang, 'rules.title')}",
        description=t(lang, "rules.desc"),
        color=COLOR_PRIMARY,
    )
    for i, (title, detail) in enumerate(rules_for(lang), 1):
        embed.add_field(name=f"`{i}.` {title}", value=detail, inline=False)
    return _footer(embed)


# ---------------------------------------------------------------------------
# !deploy
# ---------------------------------------------------------------------------
def deploy_offer_embed(user: discord.abc.User, lang: str = DEFAULT_LANG) -> discord.Embed:
    """The specs preview shown before the user presses Start."""
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {t(lang, 'deploy.title')}",
        description=t(lang, "deploy.desc", user=user.mention, os=PLAN["os"]),
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'deploy.memory')}",
        value=f"**{PLAN['ram_mb']} MB**\n`+ {PLAN['swap_mb']} MB {t(lang, 'deploy.swap')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} {t(lang, 'deploy.processor')}",
        value=f"**{PLAN['cpu_cores']:g} vCPU**\n`{t(lang, 'deploy.fair_share')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'deploy.storage')}",
        value=f"**{PLAN['disk_gb']} GB**\n`SSD`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'deploy.os')}",
        value=f"**{PLAN['os']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'generic.bandwidth')}",
        value=f"**{PLAN['bandwidth']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'deploy.access')}",
        value=t(lang, "deploy.access_value"),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'deploy.plan')}",
        value=f"`{PLAN['name']}` • {t(lang, 'deploy.location')}: `{PLAN['location']}`",
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'btn.rules')}",
        value=t(lang, "deploy.rules_field", count=len(rules_for(lang))),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} {t(lang, 'deploy.privacy')}",
        value=t(lang, "deploy.privacy_value"),
        inline=False,
    )
    return _footer(embed)


def deploy_progress_embed(
    stage_label: str, percent: int, log_lines: list[str], lang: str = DEFAULT_LANG
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['rocket']} {t(lang, 'progress.title')}",
        description=f"{progress_bar(percent)}\n\n**{stage_label}**",
        color=COLOR_WARNING,
    )
    if log_lines:
        embed.add_field(
            name=t(lang, "progress.build_log"),
            value="```ansi\n" + "\n".join(log_lines[-8:]) + "\n```",
            inline=False,
        )
    return _footer(embed)


def deploy_success_embed(
    info: dict, ssh_status: str, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """Public success card. Never contains the SSH command."""
    embed = discord.Embed(
        title=f"{EMOJI['check']} {t(lang, 'success.title')}",
        description=t(lang, "success.desc", prefix=P),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=t(lang, "generic.server_id"), value=f"`{info['short_id']}`", inline=True
    )
    embed.add_field(name=t(lang, "generic.hostname"), value=f"`{info['name']}`", inline=True)
    embed.add_field(
        name=t(lang, "generic.status"), value=status_badge(info["status"], lang), inline=True
    )

    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'generic.ram')}",
        value=f"**{info['ram_limit_mb']} MB**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} vCPU", value=f"**{info['cpu_limit']:g}**", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'generic.disk')}",
        value=f"**{info['disk_gb']} GB**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}", value=f"**{info['os']}**", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'generic.bandwidth')}",
        value=f"**{info['bandwidth']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'generic.created')}",
        value=f"<t:{int(info['created_ts'])}:R>",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'success.ssh_field')}", value=ssh_status, inline=False
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# SSH (DM only)
# ---------------------------------------------------------------------------
def ssh_dm_embed(info: dict, ssh: str, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['key']} {t(lang, 'ssh.dm_title')}",
        description=t(
            lang, "ssh.dm_desc", name=info["name"], sid=info["short_id"], ssh=ssh
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'ssh.system')}",
        value=f"{info['os']} • {info['ram_limit_mb']} MB RAM • "
        f"{info['cpu_limit']:g} vCPU • {info['disk_gb']} GB",
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} {t(lang, 'ssh.keep_private')}",
        value=t(lang, "ssh.keep_private_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def dm_failed_embed(lang: str = DEFAULT_LANG) -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['mail']} {t(lang, 'ssh.dm_failed_title')}",
            description=t(lang, "ssh.dm_failed_desc"),
            color=COLOR_WARNING,
        )
    )


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
def manage_embed(info: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    running = info["status"] == "running"
    embed = discord.Embed(
        title=f"{EMOJI['gear']} {t(lang, 'manage.title')}",
        description=t(
            lang,
            "manage.desc",
            name=info["name"],
            status=status_badge(info["status"], lang),
        ),
        color=COLOR_SUCCESS if running else COLOR_NEUTRAL,
    )

    if running:
        ram_pct = int(info["ram_used_mb"] / max(1, info["ram_limit_mb"]) * 100)
        embed.add_field(
            name=f"{EMOJI['ram']} {t(lang, 'manage.memory')}",
            value=(
                f"**{info['ram_used_mb']} MB / {info['ram_limit_mb']} MB**\n"
                f"{progress_bar(ram_pct, width=14)}"
            ),
            inline=False,
        )
        cpu_pct = int(min(100, info["cpu_percent"]))
        embed.add_field(
            name=f"{EMOJI['cpu']} {t(lang, 'generic.cpu')}",
            value=(
                f"**{info['cpu_percent']:.1f}% / {info['cpu_limit']:g} vCPU**\n"
                f"{progress_bar(cpu_pct, width=14)}"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{EMOJI['ram']} {t(lang, 'manage.memory')}",
            value=t(
                lang, "manage.allocated_offline", value=f"{info['ram_limit_mb']} MB"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"{EMOJI['cpu']} {t(lang, 'generic.cpu')}",
            value=t(
                lang, "manage.allocated_offline", value=f"{info['cpu_limit']:g} vCPU"
            ),
            inline=False,
        )

    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'generic.disk')}",
        value=f"**{info['disk_gb']} GB**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}", value=f"**{info['os']}**", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'generic.network')}",
        value=(
            f"\u2193 {info['net_rx_mb']:.1f} MB • \u2191 {info['net_tx_mb']:.1f} MB"
            if running
            else f"**{info['bandwidth']}**"
        ),
        inline=True,
    )
    embed.add_field(
        name=t(lang, "generic.server_id"), value=f"`{info['short_id']}`", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'generic.uptime')}",
        value=f"**{human_uptime(info['uptime_seconds'])}**" if running else "`—`",
        inline=True,
    )
    embed.add_field(
        name=t(lang, "generic.created"), value=f"<t:{int(info['created_ts'])}:D>", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'success.ssh_field')}",
        value=(
            t(lang, "manage.ssh_running") if running else t(lang, "manage.ssh_stopped")
        ),
        inline=False,
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Language picker
# ---------------------------------------------------------------------------
def language_embed(current: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI.get('spark', '🌐')} {t(current, 'lang.title')}",
        description=t(current, "lang.desc", current=lang_label(current)),
        color=COLOR_PRIMARY,
    )
    for code, meta in LANGUAGES.items():
        marker = " ✅" if code == current else ""
        embed.add_field(
            name=f"{meta['flag']} {meta['name']}{marker}",
            value=f"`{COMMAND_PREFIX}lang {code}`",
            inline=True,
        )
    return _footer(embed)


def language_changed_embed(lang: str) -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['check']} {t(lang, 'lang.changed_title')}",
            description=t(lang, "lang.changed"),
            color=COLOR_SUCCESS,
        )
    )


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------
def ban_embed(record: dict, vps_stopped: bool, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['hammer']} {t(lang, 'mod.banned_title')}",
        description=t(lang, "mod.banned_desc", uid=record["user_id"]),
        color=COLOR_ERROR,
    )
    embed.add_field(name=t(lang, "mod.user_id"), value=f"`{record['user_id']}`", inline=True)
    embed.add_field(
        name=t(lang, "mod.moderator"), value=f"<@{record['moderator_id']}>", inline=True
    )
    embed.add_field(name=t(lang, "generic.reason"), value=record["reason"], inline=False)
    embed.add_field(
        name=t(lang, "mod.server"),
        value=t(lang, "mod.stopped_auto") if vps_stopped else t(lang, "mod.no_server"),
        inline=False,
    )
    return _footer(embed)


def unban_embed(record: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['check']} {t(lang, 'mod.unbanned_title')}",
        description=t(lang, "mod.unbanned_desc", uid=record["user_id"]),
        color=COLOR_SUCCESS,
    )
    embed.add_field(name=t(lang, "mod.user_id"), value=f"`{record['user_id']}`", inline=True)
    embed.add_field(
        name=t(lang, "mod.prev_reason"), value=record.get("reason", "—"), inline=False
    )
    return _footer(embed)


def bans_list_embed(bans: list[dict], lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['shield']} {t(lang, 'mod.banlist_title')}",
        description=(
            t(lang, "mod.banlist_desc", count=len(bans))
            if bans
            else t(lang, "mod.banlist_empty")
        ),
        color=COLOR_NEUTRAL,
    )
    for record in bans[:20]:
        name = record.get("user_name") or f"User {record['user_id']}"
        embed.add_field(
            name=f"{name} • `{record['user_id']}`",
            value=(
                f"{t(lang, 'generic.reason')}: {record.get('reason', '—')}\n"
                f"<@{record.get('moderator_id', 0)}> • "
                f"<t:{int(record.get('ts', 0))}:R>"
            ),
            inline=False,
        )
    return _footer(embed)


def banned_notice_embed(record: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['hammer']} {t(lang, 'mod.you_banned_title')}",
        description=t(lang, "mod.you_banned_desc"),
        color=COLOR_ERROR,
    )
    embed.add_field(name=t(lang, "generic.reason"), value=record.get("reason", "—"), inline=False)
    embed.add_field(
        name=t(lang, "mod.banned_at"), value=f"<t:{int(record.get('ts', 0))}:R>", inline=True
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
def info_embed(title: str, description: str, color: int = COLOR_PRIMARY) -> discord.Embed:
    return _footer(discord.Embed(title=title, description=description, color=color))


def error_embed(
    description: str, title: str | None = None, lang: str = DEFAULT_LANG
) -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['cross']} {title or t(lang, 'generic.error_title')}",
            description=description[:4000],
            color=COLOR_ERROR,
        )
    )


def help_embed(
    prefix: str, owner: bool = False, lang: str = DEFAULT_LANG
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {BOT_NAME}",
        description=t(lang, "help.desc", version=BOT_VERSION),
        color=COLOR_PRIMARY,
    )
    embed.add_field(name=f"`{prefix}deploy`", value=t(lang, "help.deploy"), inline=False)
    embed.add_field(name=f"`{prefix}manage`", value=t(lang, "help.manage"), inline=False)
    embed.add_field(
        name=f"`{prefix}rules`",
        value=t(lang, "help.rules", count=len(rules_for(lang))),
        inline=False,
    )
    embed.add_field(name=f"`{prefix}destroy`", value=t(lang, "help.destroy"), inline=False)
    embed.add_field(name=f"`{prefix}ping`", value=t(lang, "help.ping"), inline=False)
    embed.add_field(
        name=f"`{prefix}lang` \u2022 `{prefix}язык`", value=t(lang, "help.lang"), inline=False
    )
    if owner:
        embed.add_field(
            name=f"{EMOJI['shield']} {t(lang, 'help.staff')}",
            value=(
                f"`{prefix}ban <@user|id> [reason]` • `{prefix}unban <@user|id>`\n"
                f"`{prefix}bans` • `{prefix}servers`"
            ),
            inline=False,
        )
    return _footer(embed)
