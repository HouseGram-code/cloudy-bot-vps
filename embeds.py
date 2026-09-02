"""All Discord embeds / visual formatting for Cloudy VPS Bot.

Every builder takes an optional `lang` ("en" or "ru"); strings come from i18n.py.
"""

from __future__ import annotations

import datetime as dt

import discord

from config import (
    BONUS_COOLDOWN_HOURS,
    BONUS_LEAVES,
    BOT_FOOTER,
    BOT_NAME,
    BOT_VERSION,
    COMMAND_PREFIX,
    LEAF_COST_PER_HOUR,
    LEAVES_ENABLED,
    START_LEAVES,
    VPS_EXPIRY_ACTION,
    VPS_LIFETIME_DAYS,
    COLOR_ERROR,
    COLOR_NEUTRAL,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    EMOJI,
)
from i18n import DEFAULT_LANG, LANGUAGES, lang_label, rules as rules_for
from plan_store import (
    MAX_CPU,
    MAX_DISK_GB,
    MAX_RAM_MB,
    MIN_CPU,
    MIN_DISK_GB,
    MIN_RAM_MB,
    PLAN_STORE,
)
from i18n import t

FILLED = "\u2588"
EMPTY = "\u2591"
# Softer blocks used inside the monospace "Resources" panel of !manage.
BAR_ON = "\u25b0"
BAR_OFF = "\u25b1"
LINE = "\u2500"
P = COMMAND_PREFIX


def progress_bar(percent: int, width: int = 22) -> str:
    percent = max(0, min(100, int(percent)))
    filled = round(width * percent / 100)
    return f"`{FILLED * filled}{EMPTY * (width - filled)}` **{percent}%**"


def mini_bar(percent: int, width: int = 12) -> str:
    """Plain (no backticks) bar for use inside code blocks."""
    percent = max(0, min(100, int(percent)))
    filled = round(width * percent / 100)
    return BAR_ON * filled + BAR_OFF * (width - filled)


def spec_row(label: str, bar: str, value: str, width: int = 5) -> str:
    """One aligned row of the monospace resource panel."""
    return f"{label.ljust(width)} {bar}  {value}"


def plan_state_label(lang: str = DEFAULT_LANG) -> str:
    return t(lang, "plan.default" if PLAN_STORE.is_default() else "plan.custom")


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
def profile_embed(
    user: discord.abc.User,
    wallet: dict,
    info: dict | None = None,
    lang: str = DEFAULT_LANG,
) -> discord.Embed:
    """Pretty profile card: name, ID, leaf balance, VPS and the daily bonus."""
    leaves = int(wallet.get("leaves", 0))
    cost = max(1, int(wallet.get("cost", LEAF_COST_PER_HOUR)))
    hours = int(wallet.get("hours_left", leaves // cost))
    bonus_amount = int(wallet.get("bonus_amount", BONUS_LEAVES))

    embed = discord.Embed(
        title=f"{EMOJI['user']} {t(lang, 'profile.title')}",
        description=t(lang, "profile.desc"),
        color=COLOR_PRIMARY,
    )
    embed.set_thumbnail(url=getattr(user.display_avatar, "url", None))

    embed.add_field(
        name=f"{EMOJI['user']} {t(lang, 'profile.name')}",
        value=f"**{user.display_name}**\n`{user}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['id']} {t(lang, 'profile.id')}",
        value=f"`{user.id}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['leaf']} {t(lang, 'profile.balance')}",
        value=t(lang, "profile.balance_value", leaves=leaves, cost=cost),
        inline=True,
    )

    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'profile.runtime')}",
        value=(
            # Leaves stopped limiting uptime in 1.3 Beta.
            t(lang, "profile.unlimited")
            if not LEAVES_ENABLED
            else t(lang, "profile.runtime_value", hours=hours)
            if hours > 0
            else t(lang, "profile.runtime_empty")
        ),
        inline=False,
    )

    if info:
        embed.add_field(
            name=f"{EMOJI['cloud']} {t(lang, 'profile.vps')}",
            value=t(
                lang,
                "profile.vps_yes",
                name=info.get("name", "vps"),
                status=status_badge(info.get("status", ""), lang),
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{EMOJI['cloud']} {t(lang, 'profile.vps')}",
            value=t(lang, "profile.vps_none", prefix=P),
            inline=False,
        )

    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'profile.stats')}",
        value=t(
            lang,
            "profile.stats_value",
            earned=int(wallet.get("earned", 0)),
            spent=int(wallet.get("spent", 0)),
            bonuses=int(wallet.get("bonus_count", 0)),
        ),
        inline=False,
    )
    if LEAVES_ENABLED:
        embed.add_field(
            name=f"{EMOJI['scroll']} {t(lang, 'profile.economy')}",
            value=t(
                lang,
                "profile.economy_value",
                start=START_LEAVES,
                cost=cost,
                amount=bonus_amount,
                hours=BONUS_COOLDOWN_HOURS,
                prefix=P,
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{EMOJI['leaf']} {t(lang, 'profile.economy')}",
            value=t(lang, "profile.leaves_off", days=VPS_LIFETIME_DAYS),
            inline=False,
        )
    return _footer(embed)


def bonus_claimed_embed(result: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Result card for the daily bonus (claimed or still on cooldown)."""
    cost = max(1, int(LEAF_COST_PER_HOUR))
    if result.get("ok"):
        embed = discord.Embed(
            title=f"{EMOJI['gift']} {t(lang, 'bonus.ok_title')}",
            description=t(
                lang,
                "bonus.ok",
                amount=int(result.get("amount", BONUS_LEAVES)),
                balance=int(result.get("balance", 0)),
                hours=int(result.get("balance", 0)) // cost,
                ts=int(result.get("ready_at", 0)),
            ),
            color=COLOR_SUCCESS,
        )
    else:
        embed = discord.Embed(
            title=f"{EMOJI['clock']} {t(lang, 'bonus.wait_title')}",
            description=t(
                lang,
                "bonus.wait",
                hours=BONUS_COOLDOWN_HOURS,
                amount=int(BONUS_LEAVES),
                ts=int(result.get("ready_at", 0)),
            ),
            color=COLOR_WARNING,
        )
    return _footer(embed)


def leaves_granted_embed(
    user_id: int, amount: int, balance: int, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """Staff confirmation after !give / the admin panel button."""
    key = "grant.given" if amount >= 0 else "grant.taken"
    embed = discord.Embed(
        title=f"{EMOJI['leaf']} {t(lang, 'grant.title')}",
        description=t(
            lang, key, amount=abs(int(amount)), user=int(user_id), balance=int(balance)
        ),
        color=COLOR_SUCCESS if amount >= 0 else COLOR_WARNING,
    )
    return _footer(embed)


def leaves_notice_embed(
    amount: int, balance: int, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """DM sent to the user who received leaves from staff."""
    cost = max(1, int(LEAF_COST_PER_HOUR))
    embed = discord.Embed(
        title=f"{EMOJI['gift']} {t(lang, 'grant.notice_title')}",
        description=t(
            lang,
            "grant.notice",
            amount=abs(int(amount)),
            balance=int(balance),
            hours=int(balance) // cost,
        ),
        color=COLOR_SUCCESS,
    )
    return _footer(embed)


def low_leaves_embed(balance: int, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Shown when someone tries to deploy without leaves."""
    embed = discord.Embed(
        title=f"{EMOJI['leaf']} {t(lang, 'leaves.low_title')}",
        description=t(
            lang,
            "leaves.low",
            cost=max(1, int(LEAF_COST_PER_HOUR)),
            balance=int(balance),
            amount=int(BONUS_LEAVES),
            prefix=P,
        ),
        color=COLOR_WARNING,
    )
    return _footer(embed)


def out_of_leaves_embed(name: str, lang: str = DEFAULT_LANG) -> discord.Embed:
    """DM sent when a VPS is stopped because the balance reached zero."""
    embed = discord.Embed(
        title=f"{EMOJI['offline']} {t(lang, 'billing.title')}",
        description=t(
            lang,
            "billing.desc",
            name=name,
            amount=int(BONUS_LEAVES),
            prefix=P,
        ),
        color=COLOR_WARNING,
    )
    return _footer(embed)


def about_embed(lang: str = DEFAULT_LANG, stats: dict | None = None) -> discord.Embed:
    """Pretty \"what is this bot\" card used by !about."""
    _plan = PLAN_STORE.plan()
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {BOT_NAME} \u2014 {t(lang, 'about.title')}",
        description=t(lang, "about.desc"),
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'about.specs')}",
        value=(
            f"{EMOJI['ram']} **{_plan['ram_mb']} MB** RAM \u2022 "
            f"{EMOJI['cpu']} **{_plan['cpu_cores']:g} vCPU** \u2022 "
            f"{EMOJI['disk']} **{_plan['disk_gb']} GB** SSD\n"
            f"{EMOJI['os']} `{_plan['os']}` \u2022 {EMOJI['key']} `root / web`\n"
            f"{EMOJI['net']} `{_plan['bandwidth']}` \u2022 `{_plan['name']}`"
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['rocket']} {t(lang, 'about.start')}",
        value=t(lang, "about.start_value", prefix=P),
        inline=False,
    )
    if stats:
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'admin.capacity')}",
            value=capacity_line(stats, lang),
            inline=False,
        )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'about.links')}",
        value=t(lang, "about.links_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def capacity_line(stats: dict, lang: str = DEFAULT_LANG) -> str:
    """One-line summary: `3/5 slots - 2 running - 1 stopped`."""
    return t(
        lang,
        "slots.short",
        used=int(stats.get("used", 0)),
        total=int(stats.get("slots", 0)),
        running=int(stats.get("running", 0)),
        stopped=int(stats.get("stopped", 0)),
    )


# ---------------------------------------------------------------------------
# 30-day term helpers
# ---------------------------------------------------------------------------
def term_line(lang: str = DEFAULT_LANG) -> str:
    """\"30 days free of charge\" line used by !deploy and the admin panel."""
    if VPS_LIFETIME_DAYS <= 0:
        return t(lang, "term.unlimited")
    return t(lang, "term.offer", days=VPS_LIFETIME_DAYS)


def term_status(info: dict, lang: str = DEFAULT_LANG) -> str:
    """How much of the term one server has left."""
    expires = int(float(info.get("expires_ts") or 0))
    if not expires:
        return t(lang, "term.unlimited")
    seconds = int(max(0.0, float(info.get("seconds_left") or 0)))
    if seconds <= 0:
        return t(lang, "term.expired")
    return t(
        lang,
        "term.left",
        days=seconds // 86400,
        hours=(seconds % 86400) // 3600,
        ts=expires,
    )


def deploy_offer_embed(
    user: discord.abc.User, lang: str = DEFAULT_LANG, stats: dict | None = None
) -> discord.Embed:
    """The specs preview shown before the user presses Start."""
    plan = PLAN_STORE.plan()
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {t(lang, 'deploy.title')}",
        description=t(lang, "deploy.desc", user=user.mention, os=plan["os"]),
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'deploy.memory')}",
        value=f"**{plan['ram_mb']} MB**\n`+ {plan['swap_mb']} MB {t(lang, 'deploy.swap')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} {t(lang, 'deploy.processor')}",
        value=f"**{plan['cpu_cores']:g} vCPU**\n`{t(lang, 'deploy.fair_share')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'deploy.storage')}",
        value=f"**{plan['disk_gb']} GB**\n`SSD`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'deploy.os')}",
        value=f"**{plan['os']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'generic.bandwidth')}",
        value=f"**{plan['bandwidth']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'deploy.access')}",
        value=t(lang, "deploy.access_value"),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'deploy.plan')}",
        value=f"`{plan['name']}` • {t(lang, 'deploy.location')}: `{plan['location']}`",
        inline=False,
    )
    # 1.3 Beta: every free server is granted for 30 days.
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'term.field')}",
        value=term_line(lang)
        + ("" if LEAVES_ENABLED else "\n" + t(lang, "term.no_leaves")),
        inline=False,
    )
    if stats:
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'admin.capacity')}",
            value=capacity_line(stats, lang),
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
    stage_label: str,
    percent: int,
    log_lines: list[str],
    lang: str = DEFAULT_LANG,
    location: str = "",
) -> discord.Embed:
    description = f"{progress_bar(percent)}\n\n**{stage_label}**"
    if location:
        # Keep the chosen region visible during the whole deployment.
        description += f"\n{EMOJI['net']} {t(lang, 'loc.chosen')}: **{location}**"
    embed = discord.Embed(
        title=f"{EMOJI['rocket']} {t(lang, 'progress.title')}",
        description=description,
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
    info: dict, access_status: str, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """Public success card. Never contains the access link itself."""
    embed = discord.Embed(
        title=f"{EMOJI['check']} {t(lang, 'success.title')}",
        description=t(lang, "success.desc", prefix=P),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'loc.chosen')}",
        value=location_value(LOCATIONS.get(info.get("location_id")), lang),
        inline=False,
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
        name=f"{EMOJI['gift']} {t(lang, 'term.field')}",
        value=(
            t(lang, "term.value", days=int(info.get("term_days") or VPS_LIFETIME_DAYS))
            + "\n"
            + term_status(info, lang)
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['web']} {t(lang, 'success.access_field')}",
        value=access_status,
        inline=False,
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Access delivery (DM only)
#
# a root credential, so it never touches a channel. The browser terminal
# (sshx, outbound HTTPS only) stays as a fallback for hosts that block
# ---------------------------------------------------------------------------


def sshx_dm_embed(info: dict, link: str, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Browser-terminal link (sshx). The link IS the key, so DM only."""
    embed = discord.Embed(
        title=f"{EMOJI['web']} {t(lang, 'sshx.dm_title')}",
        description=t(
            lang,
            "sshx.dm_desc",
            name=info.get("name", "-"),
            sid=info.get("short_id", "-"),
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['link']} {t(lang, 'sshx.link')}",
        value=link,
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'access.system')}",
        value=f"{info.get('os', '-')} \u2022 {info.get('ram_limit_mb', '-')} MB RAM \u2022 "
        f"{info.get('cpu_limit', 0):g} vCPU \u2022 {info.get('disk_gb', '-')} GB",
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'sshx.how')}",
        value=t(lang, "sshx.how_value"),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} {t(lang, 'sshx.keep_private')}",
        value=t(lang, "sshx.keep_private_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def specs_embed(
    info: dict,
    user: discord.abc.User | None = None,
    lang: str = DEFAULT_LANG,
) -> discord.Embed:
    """`!specs` - VPS username, RAM, disk and the rest of the hardware."""
    running = str(info.get("status", "")).lower() == "running"
    embed = discord.Embed(
        title=f"{EMOJI['cpu']} {t(lang, 'specs.title')}",
        description=t(
            lang,
            "specs.desc",
            name=info.get("name", "-"),
            status=status_badge(info.get("status", "unknown"), lang),
        ),
        color=COLOR_SUCCESS if running else COLOR_NEUTRAL,
    )

    owner_id = int(info.get("owner_id") or 0)
    owner_mention = user.mention if user is not None else (
        f"<@{owner_id}>" if owner_id else "-"
    )
    owner_name = str(user) if user is not None else (info.get("owner_name") or "")
    embed.add_field(
        name=f"{EMOJI['user']} {t(lang, 'specs.owner')}",
        value=owner_mention + (f"\n`{owner_name}`" if owner_name else ""),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'specs.user')}",
        value=t(
            lang,
            "specs.user_value",
            user=info.get("login") or info.get("ssh_user") or "root",
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['id']} {t(lang, 'generic.server_id')}",
        value=f"`{info.get('short_id', '-')}`",
        inline=True,
    )

    ram_limit = max(1, int(info.get("ram_limit_mb") or 0))
    ram_used = int(info.get("ram_used_mb") or 0) if running else 0
    ram_pct = min(100, int(ram_used * 100 / ram_limit))
    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'specs.ram')}",
        value=(
            f"`{mini_bar(ram_pct)}` "
            + t(lang, "specs.ram_value", used=ram_used, limit=ram_limit)
            if running
            else t(lang, "specs.ram_idle", limit=ram_limit)
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'specs.disk')}",
        value=t(lang, "specs.disk_value", disk=info.get("disk_gb", 0)),
        inline=True,
    )
    swap = int(info.get("swap_mb") or 0)
    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'specs.swap')}",
        value=f"**{swap} MB**" if swap else "`-`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} {t(lang, 'specs.cpu')}",
        value=t(
            lang,
            "specs.cpu_value",
            cpu=f"{float(info.get('cpu_limit') or 0):g}",
            load=f"{float(info.get('cpu_percent') or 0.0):.1f}" if running else "0.0",
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}",
        value=f"**{info.get('os', '-')}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'specs.traffic')}",
        value=(
            f"\u2193 **{float(info.get('net_rx_mb') or 0):.1f} MB** \u2022 "
            f"\u2191 **{float(info.get('net_tx_mb') or 0):.1f} MB**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'specs.uptime')}",
        value=(
            f"**{human_uptime(int(info.get('uptime_seconds') or 0))}**"
            if running
            else "`-`"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'specs.host')}",
        value=f"`{info.get('hostname') or info.get('name', '-')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gift']} {t(lang, 'term.field')}",
        value=term_status(info, lang),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['web']} {t(lang, 'specs.hint')}",
        value=t(lang, "specs.hint_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def grant_vps_embed(
    info: dict,
    owner_id: int,
    login: str = "root",
    lang: str = DEFAULT_LANG,
) -> discord.Embed:
    """Staff confirmation card for `!givevps`."""
    embed = discord.Embed(
        title=f"{EMOJI['gift']} {t(lang, 'givevps.title')}",
        description=t(
            lang, "givevps.desc", user=int(owner_id), name=info.get("name", "-")
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'givevps.login')}",
        value=t(lang, "givevps.login_value", user=login or "root"),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['id']} {t(lang, 'generic.server_id')}",
        value=f"`{info.get('short_id', '-')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}",
        value=f"`{info.get('os', 'Ubuntu 22.04 LTS')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'givevps.specs')}",
        value=t(
            lang,
            "givevps.specs_value",
            ram=int(info.get("ram_limit_mb") or 0),
            swap=int(info.get("swap_mb") or 0),
            disk=int(info.get("disk_gb") or 0),
            cpu=info.get("cpu_limit", 1),
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'term.field')}",
        value=term_status(info, lang),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'givevps.next')}",
        value=t(lang, "givevps.next_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def grant_vps_notice_embed(
    info: dict, login: str = "root", lang: str = DEFAULT_LANG
) -> discord.Embed:
    """DM for the user who just received a VPS from staff."""
    embed = discord.Embed(
        title=f"{EMOJI['rocket']} {t(lang, 'givevps.notice_title')}",
        description=t(
            lang, "givevps.notice", name=info.get("name", "-"), prefix=P
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['key']} {t(lang, 'givevps.login')}",
        value=t(lang, "givevps.login_value", user=login or "root"),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}",
        value=f"`{info.get('os', 'Ubuntu 22.04 LTS')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'givevps.specs')}",
        value=t(
            lang,
            "givevps.specs_value",
            ram=int(info.get("ram_limit_mb") or 0),
            swap=int(info.get("swap_mb") or 0),
            disk=int(info.get("disk_gb") or 0),
            cpu=info.get("cpu_limit", 1),
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'term.field')}",
        value=term_status(info, lang),
        inline=False,
    )
    return _footer(embed)


def dm_failed_embed(lang: str = DEFAULT_LANG) -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['mail']} {t(lang, 'dm.failed_title')}",
            description=t(lang, "dm.failed_desc"),
            color=COLOR_WARNING,
        )
    )


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
def manage_embed(info: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Compact, aligned control-panel card for !manage.

    Every metric lives in one monospace block, so the columns line up no
    matter how wide the values are (the old card used one field per metric
    and looked ragged).
    """
    running = info["status"] == "running"
    description = t(
        lang,
        "manage.desc",
        name=info["name"],
        status=status_badge(info["status"], lang),
    )
    if not running:
        description += "\n" + t(lang, "manage.offline_hint")

    embed = discord.Embed(
        title=f"{EMOJI['gear']} {t(lang, 'manage.title')}",
        description=description,
        color=COLOR_SUCCESS if running else COLOR_NEUTRAL,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'loc.chosen')}",
        value=location_value(LOCATIONS.get(info.get("location_id")), lang),
        inline=False,
    )

    ram_limit = max(1, int(info.get("ram_limit_mb") or 0))
    ram_used = int(info.get("ram_used_mb") or 0) if running else 0
    ram_pct = int(ram_used / ram_limit * 100)
    cpu_limit = float(info.get("cpu_limit") or 0)
    cpu_used = float(info.get("cpu_percent") or 0.0) if running else 0.0
    disk_gb = info.get("disk_gb") or 0

    rows = [
        spec_row(
            "RAM",
            mini_bar(ram_pct),
            f"{ram_used} / {ram_limit} MB" if running else f"{ram_limit} MB",
        ),
        spec_row(
            "CPU",
            mini_bar(int(min(100, cpu_used))),
            f"{cpu_used:.1f}% / {cpu_limit:g} vCPU" if running else f"{cpu_limit:g} vCPU",
        ),
        spec_row("DISK", LINE * 12, f"{disk_gb} GB SSD"),
    ]
    if running:
        rows.append(
            spec_row(
                "NET",
                LINE * 12,
                f"\u2193 {float(info.get('net_rx_mb') or 0):.1f} MB  "
                f"\u2191 {float(info.get('net_tx_mb') or 0):.1f} MB",
            )
        )
    else:
        rows.append(spec_row("NET", LINE * 12, str(info.get("bandwidth") or "-")))

    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'manage.resources')}",
        value="```\n" + "\n".join(rows) + "\n```",
        inline=False,
    )

    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'generic.os')}",
        value=f"`{info.get('os', '-')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'generic.uptime')}",
        value=(
            f"**{human_uptime(info.get('uptime_seconds') or 0)}**"
            if running
            else "`\u2014`"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cloud']} {t(lang, 'generic.created')}",
        value=f"<t:{int(info.get('created_ts') or 0)}:R>",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'generic.server_id')}",
        value=f"`{info.get('short_id', '-')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'generic.hostname')}",
        value=f"`{info.get('hostname') or info.get('name', '-')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['online'] if running else EMOJI['offline']} {t(lang, 'generic.status')}",
        value=status_badge(info["status"], lang),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['web']} {t(lang, 'success.access_field')}",
        value=(
            t(lang, "manage.web_running", prefix=P)
            if running
            else t(lang, "manage.web_stopped")
        ),
        inline=False,
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Resource plan (staff)
# ---------------------------------------------------------------------------
def plan_embed(lang: str = DEFAULT_LANG) -> discord.Embed:
    """What a new free VPS gets right now (and how to change it)."""
    plan = PLAN_STORE.plan()
    state = PLAN_STORE.state()
    embed = discord.Embed(
        title=f"{EMOJI['spark']} {t(lang, 'plan.title')}",
        description=t(lang, "plan.desc", prefix=P),
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"{EMOJI['ram']} {t(lang, 'plan.ram')}",
        value=t(lang, "plan.ram_value", ram=plan["ram_mb"], swap=plan["swap_mb"]),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} {t(lang, 'plan.cpu')}",
        value=t(lang, "plan.cpu_value", cpu=f"{plan['cpu_cores']:g}"),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'plan.disk')}",
        value=t(lang, "plan.disk_value", disk=plan["disk_gb"]),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'plan.limits')}",
        value=t(
            lang,
            "plan.limits_value",
            ram_min=MIN_RAM_MB,
            ram_max=MAX_RAM_MB,
            disk_min=MIN_DISK_GB,
            disk_max=MAX_DISK_GB,
            cpu_min=f"{MIN_CPU:g}",
            cpu_max=f"{MAX_CPU:g}",
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'plan.note')}",
        value=t(lang, "plan.note_value", prefix=P),
        inline=False,
    )
    if state.get("changed_ts"):
        embed.add_field(
            name=f"{EMOJI['clock']} {t(lang, 'admin.changed_by')}",
            value=(
                (f"<@{int(state['by_id'])}> " if state.get("by_id") else "")
                + f"<t:{int(state['changed_ts'])}:R> \u2022 `{plan_state_label(lang)}`"
            ),
            inline=False,
        )
    return _footer(embed)


def plan_changed_embed(old: dict, new: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['check']} {t(lang, 'plan.changed_title')}",
        description=t(
            lang,
            "plan.changed",
            old_ram=old.get("ram_mb"),
            ram=new.get("ram_mb"),
            old_cpu=f"{float(old.get('cpu_cores', 0)):g}",
            cpu=f"{float(new.get('cpu_cores', 0)):g}",
            old_disk=old.get("disk_gb"),
            disk=new.get("disk_gb"),
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'plan.note')}",
        value=t(lang, "plan.note_value", prefix=P),
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
        name=f"`{prefix}servers` \u2022 `{prefix}\u043c\u043e\u0438`",
        value=t(lang, "help.servers"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}status` \u2022 `{prefix}\u0441\u0442\u0430\u0442\u0443\u0441`",
        value=t(lang, "help.status"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}specs` \u2022 `{prefix}\u0441\u043f\u0435\u043a\u0438`",
        value=t(lang, "help.specs"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}sshx` \u2022 `{prefix}\u0432\u0435\u0431`",
        value=t(lang, "help.sshx"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}rules`",
        value=t(lang, "help.rules", count=len(rules_for(lang))),
        inline=False,
    )
    embed.add_field(name=f"`{prefix}destroy`", value=t(lang, "help.destroy"), inline=False)
    embed.add_field(
        name=f"`{prefix}slots` \u2022 `{prefix}\u0441\u043b\u043e\u0442\u044b`",
        value=t(lang, "help.slots"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}profile` \u2022 `{prefix}\u043f\u0440\u043e\u0444\u0438\u043b\u044c`",
        value=t(lang, "help.profile"),
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}about` \u2022 `{prefix}\u043e\u0431\u043e\u0442\u0435`",
        value=t(lang, "help.about"),
        inline=False,
    )
    embed.add_field(name=f"`{prefix}ping`", value=t(lang, "help.ping"), inline=False)
    embed.add_field(
        name=f"`{prefix}lang` \u2022 `{prefix}язык`", value=t(lang, "help.lang"), inline=False
    )
    if owner:
        embed.add_field(
            name=f"{EMOJI['shield']} {t(lang, 'help.staff')}",
            value=(
                f"`{prefix}ban <@user|id> [reason]` • `{prefix}unban <@user|id>`\n"
                f"`{prefix}bans` • `{prefix}servers`\n"
                f"`{prefix}admin` • `{prefix}maintenance on|off`\n"
                f"`{prefix}slots [+1|-1|set N]` • `{prefix}wipe <@user|id> [reason]`\n"
                f"`{prefix}givevps <@user|id> [username] [RAM] [disk] [days]`\n"
                f"\u21b3 `{prefix}givevps @user 5g 25 1` \u2014 {t(lang, 'help.givevps_hint')}\n"
                f"`{prefix}plan [ram|disk|cpu] <N>` • `{prefix}renew <@user|id> [days]`\n"
                f"`{prefix}deploylock on|off|status [min] [reason]` \u2014 "
                f"{t(lang, 'help.deploylock')}\n"
                f"`{prefix}servers all` • `{prefix}status`"
            ),
            inline=False,
        )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Maintenance mode / admin panel
# ---------------------------------------------------------------------------
def maintenance_embed(state: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """The friendly \"we are working on the servers\" notice regular users see."""
    reason = (state.get("reason") or "").strip() or t(lang, "maint.default_reason")
    embed = discord.Embed(
        title=f"\U0001F6A7 {t(lang, 'maint.title')}",
        description=(
            f"{EMOJI['gear']} **{t(lang, 'maint.headline')}**\n\n"
            f"{t(lang, 'maint.body', prefix=P)}"
        ),
        color=COLOR_WARNING,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'maint.what')}",
        value=f">>> {reason}",
        inline=False,
    )
    since = state.get("since") or 0
    if since:
        embed.add_field(
            name=f"{EMOJI['clock']} {t(lang, 'maint.since')}",
            value=f"<t:{int(since)}:R>",
            inline=True,
        )
    eta = (state.get("eta") or "").strip()
    if eta:
        embed.add_field(
            name=f"\u23F3 {t(lang, 'maint.eta')}", value=eta, inline=True
        )
    embed.add_field(
        name=f"{EMOJI['check']} {t(lang, 'maint.available')}",
        value=t(lang, "maint.available_value", prefix=P),
        inline=False,
    )
    embed.set_footer(text=f"{BOT_FOOTER} \u2022 {t(lang, 'maint.footer_note')}")
    embed.timestamp = dt.datetime.now(dt.timezone.utc)
    return embed


def slots_embed(stats: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Public capacity card: running / stopped / slots (e.g. 5/5)."""
    used = int(stats.get("used", 0))
    total = max(1, int(stats.get("slots", 0)))
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {t(lang, 'slots.title')}",
        description=(
            t(
                lang,
                "slots.desc",
                used=used,
                total=int(stats.get("slots", 0)),
                free=int(stats.get("free", 0)),
            )
            + "\n"
            + progress_bar(int(used * 100 / total))
        ),
        color=COLOR_ERROR if stats.get("full") else COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['online']} {t(lang, 'slots.running')}",
        value=f"**{int(stats.get('running', 0))}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['offline']} {t(lang, 'slots.stopped')}",
        value=f"**{int(stats.get('stopped', 0))}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'slots.free')}",
        value=f"**{int(stats.get('free', 0))}**",
        inline=True,
    )
    if stats.get("full"):
        embed.add_field(
            name=f"{EMOJI['lock']} {t(lang, 'slots.full_title')}",
            value=t(lang, "slots.full", total=int(stats.get("slots", 0)), prefix=P),
            inline=False,
        )
    return _footer(embed)


def slots_changed_embed(
    old: int, stats: dict, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """Confirmation shown after staff raised / lowered the slot limit."""
    used = int(stats.get("used", 0))
    new = int(stats.get("slots", 0))
    embed = discord.Embed(
        title=f"{EMOJI['gear']} {t(lang, 'slots.changed_title')}",
        description=t(lang, "slots.changed", old=int(old), new=new, used=used),
        color=COLOR_SUCCESS,
    )
    if used > new:
        embed.add_field(
            name=f"{EMOJI['pending']} {t(lang, 'slots.full_title')}",
            value=t(lang, "slots.below_used", used=used),
            inline=False,
        )
    return _footer(embed)


def vps_wiped_embed(
    user_id: int, stats: dict, lang: str = DEFAULT_LANG
) -> discord.Embed:
    """Staff confirmation after deleting somebody else's VPS."""
    embed = discord.Embed(
        title=f"{EMOJI['hammer']} {t(lang, 'wipe.title')}",
        description=t(
            lang,
            "wipe.done",
            user=int(user_id),
            free=int(stats.get("free", 0)),
            total=int(stats.get("slots", 0)),
        ),
        color=COLOR_SUCCESS,
    )
    return _footer(embed)


def vps_wiped_notice_embed(reason: str = "", lang: str = DEFAULT_LANG) -> discord.Embed:
    """DM sent to the owner whose VPS was removed by staff."""
    embed = discord.Embed(
        title=f"{EMOJI['cross']} {t(lang, 'wipe.notice_title')}",
        description=t(
            lang,
            "wipe.notice",
            reason=(reason or "").strip() or t(lang, "wipe.no_reason"),
            prefix=P,
        ),
        color=COLOR_ERROR,
    )
    return _footer(embed)


def admin_panel_embed(
    state: dict,
    servers: int = 0,
    ban_count: int = 0,
    lang: str = DEFAULT_LANG,
    stats: dict | None = None,
) -> discord.Embed:
    """Staff-only control panel with the maintenance switch."""
    on = bool(state.get("enabled"))
    embed = discord.Embed(
        title=f"{EMOJI['shield']} {t(lang, 'admin.title')}",
        description=t(lang, "admin.desc", bot=BOT_NAME),
        color=COLOR_WARNING if on else COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"\U0001F6A7 {t(lang, 'admin.mode')}",
        value=(
            f"{EMOJI['pending']} {t(lang, 'admin.mode_on')}"
            if on
            else f"{EMOJI['online']} {t(lang, 'admin.mode_off')}"
        ),
        inline=False,
    )
    if on:
        reason = (state.get("reason") or "").strip() or t(lang, "maint.default_reason")
        embed.add_field(
            name=f"{EMOJI['scroll']} {t(lang, 'maint.what')}",
            value=f">>> {reason}",
            inline=False,
        )
    if state.get("since"):
        embed.add_field(
            name=f"{EMOJI['clock']} {t(lang, 'maint.since')}",
            value=f"<t:{int(state['since'])}:R>",
            inline=True,
        )
    if state.get("by_id"):
        embed.add_field(
            name=f"{EMOJI['hammer']} {t(lang, 'admin.changed_by')}",
            value=f"<@{int(state['by_id'])}>",
            inline=True,
        )
    embed.add_field(
        name=f"{EMOJI['cloud']} {t(lang, 'admin.servers')}",
        value=f"**{servers}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} {t(lang, 'admin.bans')}",
        value=f"**{ban_count}**",
        inline=True,
    )
    _plan = PLAN_STORE.plan()
    embed.add_field(
        name=f"{EMOJI['cpu']} {t(lang, 'admin.resources')}",
        value=t(
            lang,
            "admin.resources_value",
            ram=_plan["ram_mb"],
            cpu=f"{_plan['cpu_cores']:g}",
            disk=_plan["disk_gb"],
            state=plan_state_label(lang),
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['gift']} {t(lang, 'admin.term')}",
        value=(
            t(
                lang,
                "admin.term_value",
                days=VPS_LIFETIME_DAYS,
                action=VPS_EXPIRY_ACTION,
            )
            if VPS_LIFETIME_DAYS > 0
            else t(lang, "admin.term_unlimited")
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['leaf']} {t(lang, 'admin.leaves')}",
        value=(
            t(
                lang,
                "admin.leaves_value",
                start=START_LEAVES,
                cost=LEAF_COST_PER_HOUR,
                amount=BONUS_LEAVES,
                hours=BONUS_COOLDOWN_HOURS,
            )
            if LEAVES_ENABLED
            else t(lang, "admin.leaves_off")
        ),
        inline=False,
    )
    if stats:
        used = int(stats.get("used", 0))
        total = int(stats.get("slots", 0))
        embed.add_field(
            name=f"{EMOJI['spark']} {t(lang, 'admin.capacity')}",
            value=(
                f"**{used}/{total}**"
                + (f" {EMOJI['lock']}" if stats.get("full") else "")
            ),
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI['online']} {t(lang, 'admin.running')}",
            value=f"**{int(stats.get('running', 0))}**",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI['offline']} {t(lang, 'admin.stopped')}",
            value=f"**{int(stats.get('stopped', 0))}**",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'slots.free')}",
            value=f"**{int(stats.get('free', 0))}**",
            inline=True,
        )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'admin.hint')}",
        value=t(lang, "admin.hint_value", prefix=P),
        inline=False,
    )
    return _footer(embed)


def maintenance_toggled_embed(
    state: dict, lang: str = DEFAULT_LANG
) -> discord.Embed:
    on = bool(state.get("enabled"))
    embed = discord.Embed(
        title=(
            f"\U0001F6A7 {t(lang, 'admin.enabled_title')}"
            if on
            else f"{EMOJI['check']} {t(lang, 'admin.disabled_title')}"
        ),
        description=(
            t(lang, "admin.enabled_desc") if on else t(lang, "admin.disabled_desc")
        ),
        color=COLOR_WARNING if on else COLOR_SUCCESS,
    )
    if on:
        reason = (state.get("reason") or "").strip() or t(lang, "maint.default_reason")
        embed.add_field(
            name=f"{EMOJI['scroll']} {t(lang, 'maint.what')}",
            value=f">>> {reason}",
            inline=False,
        )
    return _footer(embed)


# ---------------------------------------------------------------------------
# 1.4 Beta (dev): regions, servers panel, service status, abuse guard
# ---------------------------------------------------------------------------
from config import OS_CHOICES, VPS_LIFETIME_DAYS as _TERM_DAYS  # noqa: E402
from locations import LOCATIONS  # noqa: E402
from locations import title as location_title  # noqa: E402


def location_line(loc: dict, lang: str = DEFAULT_LANG) -> str:
    """One region row: flag, name, measured ping, colored status."""
    capacity = int(loc.get("capacity") or 0)
    free = max(0, capacity - int(loc.get("used") or 0))
    parts = [
        f"{loc.get('emoji', '')} **{location_title(loc, lang)}**",
        f"`{int(loc.get('ping') or 0)} ms`",
        t(lang, loc.get("status_key") or "loc.status_ok"),
    ]
    if loc.get("available"):
        parts.append(t(lang, "loc.free", free=free, total=capacity))
    else:
        parts.append(t(lang, "loc.reopen", minutes=int(loc.get("reopen_minutes") or 5)))
    return " \u00b7 ".join(parts)


def location_value(loc: dict, lang: str = DEFAULT_LANG) -> str:
    """Value of the \"Location\" field on a server card."""
    return (
        f"{loc.get('emoji', '')} **{location_title(loc, lang)}** \u00b7 `{loc.get('code', '-')}`\n"
        + t(lang, "loc.ping_value", ping=int(loc.get("ping") or 0))
    )


def location_of(record: dict, lang: str = DEFAULT_LANG) -> dict:
    """Live region data for one VPS record / info dict."""
    return LOCATIONS.get((record or {}).get("location_id"))


def os_line(choice: dict, lang: str = DEFAULT_LANG) -> str:
    mark = EMOJI["check"] if choice.get("available") else EMOJI["clock"]
    tail = (
        t(lang, "os.recommended")
        if choice.get("available") and choice.get("recommended")
        else ("" if choice.get("available") else t(lang, "os.soon"))
    )
    line = f"{mark} **{choice.get('label', '-')}** \u00b7 `{choice.get('codename', '')}`"
    return f"{line} \u00b7 {tail}" if tail else line


def deploy_location_embed(
    user: discord.abc.User,
    lang: str = DEFAULT_LANG,
    locations: list | None = None,
    stats: dict | None = None,
) -> discord.Embed:
    """Step 1 of `!deploy`: the region picker with live ping."""
    items = list(locations or LOCATIONS.all())
    open_count = sum(1 for item in items if item.get("available"))
    embed = discord.Embed(
        title=f"{EMOJI['net']} {t(lang, 'loc.title')}",
        description=t(
            lang,
            "loc.desc",
            user=user.mention,
            count=len(items),
            open=open_count,
        ),
        color=COLOR_PRIMARY,
    )
    embed.set_author(name=t(lang, "wizard.step", step=1, total=3))
    embed.add_field(
        name=f"{EMOJI['cloud']} {t(lang, 'loc.field')}",
        value="\n".join(location_line(item, lang) for item in items),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'loc.legend_field')}",
        value=t(lang, "loc.legend"),
        inline=False,
    )
    if not open_count:
        embed.add_field(
            name=f"{EMOJI['clock']} {t(lang, 'loc.status_down')}",
            value=t(lang, "loc.all_closed"),
            inline=False,
        )
    if stats:
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'admin.capacity')}",
            value=capacity_line(stats, lang),
            inline=False,
        )
    return _footer(embed)


def deploy_os_embed(
    loc: dict, lang: str = DEFAULT_LANG, choices: list | None = None
) -> discord.Embed:
    """Step 2 of `!deploy`: pick the Ubuntu release."""
    items = list(choices or OS_CHOICES)
    embed = discord.Embed(
        title=f"{EMOJI['os']} {t(lang, 'os.title')}",
        description=t(lang, "os.desc", loc=location_title(loc, lang)),
        color=COLOR_PRIMARY,
    )
    embed.set_author(name=t(lang, "wizard.step", step=2, total=3))
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'loc.chosen')}",
        value=location_value(loc, lang),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} {t(lang, 'os.field')}",
        value="\n".join(os_line(item, lang) for item in items),
        inline=False,
    )
    return _footer(embed)


def deploy_confirm_embed(
    loc: dict,
    choice: dict,
    lang: str = DEFAULT_LANG,
    stats: dict | None = None,
) -> discord.Embed:
    """Step 3 of `!deploy`: what exactly will be created."""
    plan = PLAN_STORE.plan()
    embed = discord.Embed(
        title=f"{EMOJI['rocket']} {t(lang, 'confirm.title')}",
        description=t(
            lang,
            "confirm.desc",
            os=choice.get("label", "-"),
            loc=location_title(loc, lang),
            ping=int(loc.get("ping") or 0),
            days=int(VPS_LIFETIME_DAYS),
        ),
        color=COLOR_SUCCESS,
    )
    embed.set_author(name=t(lang, "wizard.step", step=3, total=3))
    embed.add_field(
        name=f"{EMOJI['net']} {t(lang, 'loc.chosen')}",
        value=location_value(loc, lang),
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} {t(lang, 'os.chosen')}",
        value=f"**{choice.get('label', '-')}**\n`{choice.get('codename', '')}`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'deploy.plan')}",
        value=(
            f"{EMOJI['ram']} **{plan['ram_mb']} MB** \u00b7 "
            f"{EMOJI['cpu']} **{plan['cpu_cores']:g} vCPU** \u00b7 "
            f"{EMOJI['disk']} **{plan['disk_gb']} GB**"
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'term.field')}",
        value=term_line(lang),
        inline=False,
    )
    if stats:
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'admin.capacity')}",
            value=capacity_line(stats, lang),
            inline=False,
        )
    return _footer(embed)


def deploy_closed_embed(state: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Shown to users while staff keeps `!deploy` closed."""
    embed = discord.Embed(
        title=f"{EMOJI['lock']} {t(lang, 'lock.closed_title')}",
        description=t(lang, "lock.closed_desc", prefix=P),
        color=COLOR_WARNING,
    )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'lock.reason')}",
        value=(state.get("reason") or "").strip() or t(lang, "lock.no_reason"),
        inline=False,
    )
    minutes = int(state.get("minutes_left") or 0)
    embed.add_field(
        name=f"{EMOJI['clock']} {t(lang, 'lock.until')}",
        value=(
            t(lang, "lock.until_value", minutes=minutes)
            if minutes
            else t(lang, "lock.manual")
        ),
        inline=False,
    )
    return _footer(embed)


def deploy_lock_embed(state: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Staff confirmation card for `!deploylock`."""
    closed = bool(state.get("closed"))
    embed = discord.Embed(
        title=f"{EMOJI['lock'] if closed else EMOJI['check']} {t(lang, 'lock.toggled_title')}",
        description=t(
            lang,
            "lock.toggled_desc",
            prefix=P,
            state=t(lang, "lock.state_closed" if closed else "lock.state_open"),
        ),
        color=COLOR_WARNING if closed else COLOR_SUCCESS,
    )
    if closed:
        embed.add_field(
            name=f"{EMOJI['scroll']} {t(lang, 'lock.reason')}",
            value=(state.get("reason") or "").strip() or t(lang, "lock.no_reason"),
            inline=True,
        )
        minutes = int(state.get("minutes_left") or 0)
        embed.add_field(
            name=f"{EMOJI['clock']} {t(lang, 'lock.until')}",
            value=(
                t(lang, "lock.until_value", minutes=minutes)
                if minutes
                else t(lang, "lock.manual")
            ),
            inline=True,
        )
    if state.get("by_name"):
        embed.add_field(
            name=f"{EMOJI['user']} {t(lang, 'lock.by')}",
            value=f"`{state['by_name']}`",
            inline=False,
        )
    return _footer(embed)


def servers_list_embed(
    user: discord.abc.User,
    records: list,
    lang: str = DEFAULT_LANG,
    stats: dict | None = None,
) -> discord.Embed:
    """`!servers`: how many machines the user owns."""
    items = list(records or [])
    if not items:
        embed = discord.Embed(
            title=f"{EMOJI['cloud']} {t(lang, 'servers.none_title')}",
            description=t(lang, "servers.none", prefix=P, days=int(VPS_LIFETIME_DAYS)),
            color=COLOR_NEUTRAL,
        )
        return _footer(embed)

    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {t(lang, 'servers.title')}",
        description=t(lang, "servers.desc", count=len(items)),
        color=COLOR_PRIMARY,
    )
    lines = []
    for index, record in enumerate(items[:25], start=1):
        loc = location_of(record, lang)
        lines.append(
            f"`{index}.` **`{record.get('name', '-')}`**\n"
            f"\u21b3 {loc.get('emoji', '')} {location_title(loc, lang)} \u00b7 "
            f"{int(record.get('ram_mb') or 0)} MB \u00b7 {int(record.get('disk_gb') or 0)} GB \u00b7 "
            f"<t:{int(record.get('created_ts') or 0)}:R>"
        )
    embed.add_field(
        name=f"{EMOJI['gear']} {t(lang, 'servers.field')}",
        value="\n".join(lines),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'servers.hint')}",
        value=f"`{P}manage` \u00b7 `{P}sshx` \u00b7 `{P}specs`",
        inline=False,
    )
    if stats:
        embed.add_field(
            name=f"{EMOJI['cloud']} {t(lang, 'admin.capacity')}",
            value=capacity_line(stats, lang),
            inline=False,
        )
    return _footer(embed)


def server_delete_confirm_embed(info: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    loc = location_of(info, lang)
    embed = discord.Embed(
        title=f"{EMOJI['cross']} {t(lang, 'servers.delete_title')}",
        description=t(
            lang,
            "servers.delete_desc",
            name=info.get("name", "-"),
            loc=location_title(loc, lang),
        ),
        color=COLOR_ERROR,
    )
    return _footer(embed)


def server_deleted_embed(name: str, lang: str = DEFAULT_LANG) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['check']} {t(lang, 'servers.deleted_title')}",
        description=t(lang, "servers.deleted", name=name, prefix=P),
        color=COLOR_SUCCESS,
    )
    return _footer(embed)


def status_embed(
    rows: list,
    overall: str = "ok",
    lang: str = DEFAULT_LANG,
    has_image: bool = True,
) -> discord.Embed:
    """`!status`: the text half of the service-status answer."""
    colors = {"ok": COLOR_SUCCESS, "load": COLOR_WARNING, "down": COLOR_ERROR}
    emojis = {"ok": EMOJI["online"], "load": EMOJI["pending"], "down": EMOJI["offline"]}
    embed = discord.Embed(
        title=f"{emojis.get(overall, EMOJI['online'])} {t(lang, 'status.title')}",
        description=(
            f"**{t(lang, 'status.overall_' + overall)}**\n"
            + t(lang, "status.desc")
        ),
        color=colors.get(overall, COLOR_SUCCESS),
    )

    section = ""
    lines: list[str] = []
    for row in rows or []:
        if row.get("section"):
            if lines:
                embed.add_field(name=section, value="\n".join(lines), inline=False)
                lines = []
            section = f"{EMOJI['gear']} {row['section']}"
            continue
        badge = {"ok": "\U0001F7E9", "load": "\U0001F7E8", "down": "\U0001F7E5"}.get(
            row.get("status", "ok"), "\U0001F7E9"
        )
        detail = row.get("detail")
        lines.append(
            f"{badge} **{row.get('label', '-')}** \u00b7 {row.get('text', '')}"
            + (f" \u00b7 `{detail}`" if detail else "")
        )
    if lines:
        embed.add_field(name=section or t(lang, "status.core"), value="\n".join(lines), inline=False)

    embed.add_field(
        name=f"{EMOJI['spark']} {t(lang, 'loc.legend_field')}",
        value=t(lang, "status.legend"),
        inline=False,
    )
    if not has_image:
        embed.add_field(
            name=f"{EMOJI['cross']} {t(lang, 'status.no_image')}",
            value=f"`pip install -r requirements.txt`",
            inline=False,
        )
    return _footer(embed)


def guard_warning_embed(incident: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """DM sent to the owner when the abuse guard fires."""
    kind = t(lang, "guard.kind_" + str(incident.get("kind") or "miner"))
    embed = discord.Embed(
        title=f"{EMOJI['shield']} {t(lang, 'guard.warn_title')}",
        description=t(
            lang,
            "guard.warn_desc",
            kind=kind,
            name=incident.get("container", "-"),
        ),
        color=COLOR_ERROR,
    )
    action = str(incident.get("action") or "killed")
    embed.add_field(
        name=f"{EMOJI['hammer']} {t(lang, 'guard.warn_field')}",
        value=t(lang, "guard.action_" + (action if action in ("killed", "stopped", "warned") else "killed"), prefix=P),
        inline=False,
    )
    details = []
    if incident.get("processes"):
        details.append("`" + "`, `".join(str(p) for p in incident["processes"][:5]) + "`")
    if incident.get("pool_ports"):
        details.append("TCP `" + "`, `".join(str(p) for p in incident["pool_ports"]) + "`")
    if incident.get("cpu_percent"):
        details.append(f"CPU `{incident['cpu_percent']}%`")
    if details:
        embed.add_field(
            name=f"{EMOJI['gear']} {t(lang, 'generic.status')}",
            value=" \u00b7 ".join(details),
            inline=False,
        )
    embed.add_field(
        name=f"{EMOJI['scroll']} {t(lang, 'guard.strikes')}",
        value=f"**{int(incident.get('strikes') or 1)}** \u00b7 `{P}rules`",
        inline=False,
    )
    return _footer(embed)


def guard_report_embed(incident: dict, lang: str = DEFAULT_LANG) -> discord.Embed:
    """Short staff-facing line about one incident."""
    kind = t(lang, "guard.kind_" + str(incident.get("kind") or "miner"))
    embed = discord.Embed(
        title=f"{EMOJI['shield']} {t(lang, 'guard.report_title')}",
        description=t(
            lang,
            "guard.report_desc",
            kind=kind,
            name=incident.get("container", "-"),
            owner=int(incident.get("owner_id") or 0),
            action=str(incident.get("action") or "-"),
        ),
        color=COLOR_WARNING,
    )
    return _footer(embed)
