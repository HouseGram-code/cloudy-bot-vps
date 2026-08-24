"""All Discord embeds / visual formatting for Cloudy VPS Bot."""

from __future__ import annotations

import datetime as dt

import discord

from config import (
    BOT_FOOTER,
    BOT_NAME,
    BOT_VERSION,
    COLOR_ERROR,
    COLOR_NEUTRAL,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    EMOJI,
    PLAN,
    RULES,
)

FILLED = "\u2588"
EMPTY = "\u2591"


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


def status_badge(status: str) -> str:
    status = (status or "unknown").lower()
    if status == "running":
        return f"{EMOJI['online']} **Online**"
    if status in ("exited", "created", "dead"):
        return f"{EMOJI['offline']} **Offline**"
    return f"{EMOJI['pending']} **{status.capitalize()}**"


def _footer(embed: discord.Embed) -> discord.Embed:
    embed.set_footer(text=BOT_FOOTER)
    embed.timestamp = dt.datetime.now(dt.timezone.utc)
    return embed


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def rules_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['scroll']} Free VPS — Rules",
        description=(
            "By deploying a server you agree to all of the rules below.\n"
            "Breaking any of them means an instant **ban** and server removal."
        ),
        color=COLOR_PRIMARY,
    )
    for i, (title, detail) in enumerate(RULES, 1):
        embed.add_field(name=f"`{i}.` {title}", value=detail, inline=False)
    return _footer(embed)


# ---------------------------------------------------------------------------
# !deploy
# ---------------------------------------------------------------------------
def deploy_offer_embed(user: discord.abc.User) -> discord.Embed:
    """The specs preview shown before the user presses Start."""
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} Free VPS — Deployment",
        description=(
            f"Hey {user.mention}, you are about to deploy a **free VPS** on "
            f"**{PLAN['os']}**.\n"
            "Review the specifications below and press **Start** when you are ready."
        ),
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"{EMOJI['ram']} Memory (RAM)",
        value=f"**{PLAN['ram_mb']} MB**\n`+ {PLAN['swap_mb']} MB swap`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} Processor",
        value=f"**{PLAN['cpu_cores']:g} vCPU**\n`fair-share`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} Storage",
        value=f"**{PLAN['disk_gb']} GB**\n`SSD`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} Operating system",
        value=f"**{PLAN['os']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} Bandwidth",
        value=f"**{PLAN['bandwidth']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['key']} Access",
        value="**tmate SSH**\n`sent to your DMs`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} Plan",
        value=f"`{PLAN['name']}` • Location: `{PLAN['location']}`",
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['scroll']} Rules",
        value=(
            f"Pressing **Start** means you accept all **{len(RULES)} rules**.\n"
            "Press **Rules** to read them first."
        ),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} Privacy",
        value="Your SSH command is **never posted in a channel** — only in your DMs.",
        inline=False,
    )
    return _footer(embed)


def deploy_progress_embed(stage_label: str, percent: int, log_lines: list[str]) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['rocket']} Deploying your VPS\u2026",
        description=f"{progress_bar(percent)}\n\n**{stage_label}**",
        color=COLOR_WARNING,
    )
    if log_lines:
        embed.add_field(
            name="Build log",
            value="```ansi\n" + "\n".join(log_lines[-8:]) + "\n```",
            inline=False,
        )
    return _footer(embed)


def deploy_success_embed(info: dict, ssh_status: str) -> discord.Embed:
    """Public success card. Never contains the SSH command."""
    embed = discord.Embed(
        title=f"{EMOJI['check']} VPS deployed successfully!",
        description=(
            "Your free VPS is **online** and ready to use.\n"
            "Manage it any time with `!manage`."
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(name="Server ID", value=f"`{info['short_id']}`", inline=True)
    embed.add_field(name="Hostname", value=f"`{info['name']}`", inline=True)
    embed.add_field(name="Status", value=status_badge(info["status"]), inline=True)

    embed.add_field(name=f"{EMOJI['ram']} RAM", value=f"**{info['ram_limit_mb']} MB**", inline=True)
    embed.add_field(name=f"{EMOJI['cpu']} vCPU", value=f"**{info['cpu_limit']:g}**", inline=True)
    embed.add_field(name=f"{EMOJI['disk']} Disk", value=f"**{info['disk_gb']} GB**", inline=True)
    embed.add_field(name=f"{EMOJI['os']} OS", value=f"**{info['os']}**", inline=True)
    embed.add_field(
        name=f"{EMOJI['net']} Bandwidth", value=f"**{info['bandwidth']}**", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['clock']} Created", value=f"<t:{int(info['created_ts'])}:R>", inline=True
    )
    embed.add_field(
        name=f"{EMOJI['key']} SSH access (tmate)", value=ssh_status, inline=False
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# SSH (DM only)
# ---------------------------------------------------------------------------
def ssh_dm_embed(info: dict, ssh: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['key']} Your VPS — SSH access",
        description=(
            f"Server **{info['name']}** • `{info['short_id']}`\n\n"
            "Paste this in your terminal to connect as `root`:\n"
            f"```bash\n{ssh}\n```"
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(
        name=f"{EMOJI['os']} System",
        value=f"{info['os']} • {info['ram_limit_mb']} MB RAM • "
        f"{info['cpu_limit']:g} vCPU • {info['disk_gb']} GB",
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI['lock']} Keep it private",
        value=(
            "Anyone with this line gets **full root access** to your server.\n"
            "Stopping or restarting the VPS invalidates it — press **Get SSH** in "
            "`!manage` for a fresh one."
        ),
        inline=False,
    )
    return _footer(embed)


def dm_failed_embed() -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['mail']} I cannot DM you",
            description=(
                "Your SSH command is only ever sent privately, but your DMs are closed.\n\n"
                "**Fix it:** Server settings → *Privacy Settings* → enable "
                "**Direct Messages**, then press **Get SSH** again."
            ),
            color=COLOR_WARNING,
        )
    )


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
def manage_embed(info: dict) -> discord.Embed:
    running = info["status"] == "running"
    embed = discord.Embed(
        title=f"{EMOJI['gear']} VPS Control Panel",
        description=(
            f"**{info['name']}** • {status_badge(info['status'])}\n"
            "Use the buttons below to control your server."
        ),
        color=COLOR_SUCCESS if running else COLOR_NEUTRAL,
    )

    if running:
        ram_pct = int(info["ram_used_mb"] / max(1, info["ram_limit_mb"]) * 100)
        embed.add_field(
            name=f"{EMOJI['ram']} Memory",
            value=(
                f"**{info['ram_used_mb']} MB / {info['ram_limit_mb']} MB**\n"
                f"{progress_bar(ram_pct, width=14)}"
            ),
            inline=False,
        )
        cpu_pct = int(min(100, info["cpu_percent"]))
        embed.add_field(
            name=f"{EMOJI['cpu']} CPU",
            value=(
                f"**{info['cpu_percent']:.1f}% of {info['cpu_limit']:g} vCPU**\n"
                f"{progress_bar(cpu_pct, width=14)}"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{EMOJI['ram']} Memory",
            value=f"**{info['ram_limit_mb']} MB** allocated • `server offline`",
            inline=False,
        )
        embed.add_field(
            name=f"{EMOJI['cpu']} CPU",
            value=f"**{info['cpu_limit']:g} vCPU** allocated • `server offline`",
            inline=False,
        )

    embed.add_field(name=f"{EMOJI['disk']} Disk", value=f"**{info['disk_gb']} GB**", inline=True)
    embed.add_field(name=f"{EMOJI['os']} OS", value=f"**{info['os']}**", inline=True)
    embed.add_field(
        name=f"{EMOJI['net']} Network",
        value=(
            f"\u2193 {info['net_rx_mb']:.1f} MB • \u2191 {info['net_tx_mb']:.1f} MB"
            if running
            else f"**{info['bandwidth']}**"
        ),
        inline=True,
    )
    embed.add_field(name="Server ID", value=f"`{info['short_id']}`", inline=True)
    embed.add_field(
        name=f"{EMOJI['clock']} Uptime",
        value=f"**{human_uptime(info['uptime_seconds'])}**" if running else "`—`",
        inline=True,
    )
    embed.add_field(name="Created", value=f"<t:{int(info['created_ts'])}:D>", inline=True)
    embed.add_field(
        name=f"{EMOJI['key']} SSH access (tmate)",
        value=(
            f"Press **Get SSH** — the command is sent to your **DMs** only."
            if running
            else "Start the server first, then press **Get SSH**."
        ),
        inline=False,
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------
def ban_embed(record: dict, vps_stopped: bool) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['hammer']} User banned",
        description=f"<@{record['user_id']}> can no longer use the bot.",
        color=COLOR_ERROR,
    )
    embed.add_field(name="User ID", value=f"`{record['user_id']}`", inline=True)
    embed.add_field(name="Moderator", value=f"<@{record['moderator_id']}>", inline=True)
    embed.add_field(name="Reason", value=record["reason"], inline=False)
    embed.add_field(
        name="Server",
        value="Stopped automatically" if vps_stopped else "No running server",
        inline=False,
    )
    return _footer(embed)


def unban_embed(record: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['check']} User unbanned",
        description=f"<@{record['user_id']}> can use the bot again.",
        color=COLOR_SUCCESS,
    )
    embed.add_field(name="User ID", value=f"`{record['user_id']}`", inline=True)
    embed.add_field(name="Previous reason", value=record.get("reason", "—"), inline=False)
    return _footer(embed)


def bans_list_embed(bans: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['shield']} Ban list",
        description=f"**{len(bans)}** banned user(s)." if bans else "Nobody is banned.",
        color=COLOR_NEUTRAL,
    )
    for record in bans[:20]:
        name = record.get("user_name") or f"User {record['user_id']}"
        embed.add_field(
            name=f"{name} • `{record['user_id']}`",
            value=(
                f"Reason: {record.get('reason', '—')}\n"
                f"By <@{record.get('moderator_id', 0)}> • "
                f"<t:{int(record.get('ts', 0))}:R>"
            ),
            inline=False,
        )
    return _footer(embed)


def banned_notice_embed(record: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['hammer']} You are banned",
        description=(
            "You can no longer deploy or manage servers with this bot.\n"
            "Contact the staff if you think this is a mistake."
        ),
        color=COLOR_ERROR,
    )
    embed.add_field(name="Reason", value=record.get("reason", "—"), inline=False)
    embed.add_field(
        name="Banned", value=f"<t:{int(record.get('ts', 0))}:R>", inline=True
    )
    return _footer(embed)


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
def info_embed(title: str, description: str, color: int = COLOR_PRIMARY) -> discord.Embed:
    return _footer(discord.Embed(title=title, description=description, color=color))


def error_embed(description: str, title: str = "Something went wrong") -> discord.Embed:
    return _footer(
        discord.Embed(
            title=f"{EMOJI['cross']} {title}",
            description=description[:4000],
            color=COLOR_ERROR,
        )
    )


def help_embed(prefix: str, owner: bool = False) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['cloud']} {BOT_NAME}",
        description=f"Free VPS hosting, right from Discord.\nVersion **{BOT_VERSION}**",
        color=COLOR_PRIMARY,
    )
    embed.add_field(
        name=f"`{prefix}deploy`",
        value="Show the free plan specifications and deploy a new VPS.",
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}manage`",
        value="Live server info + Start / Stop / Restart / Get SSH buttons.",
        inline=False,
    )
    embed.add_field(
        name=f"`{prefix}rules`", value=f"The {len(RULES)} rules of the free tier.", inline=False
    )
    embed.add_field(name=f"`{prefix}destroy`", value="Delete your VPS.", inline=False)
    embed.add_field(name=f"`{prefix}ping`", value="Check bot latency.", inline=False)
    if owner:
        embed.add_field(
            name=f"{EMOJI['shield']} Staff only",
            value=(
                f"`{prefix}ban <@user|id> [reason]` • `{prefix}unban <@user|id>`\n"
                f"`{prefix}bans` • `{prefix}servers`"
            ),
            inline=False,
        )
    return _footer(embed)
