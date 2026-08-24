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
    if status in ("restarting", "paused"):
        return f"{EMOJI['pending']} **{status.capitalize()}**"
    return f"{EMOJI['pending']} **{status.capitalize()}**"


def _footer(embed: discord.Embed) -> discord.Embed:
    embed.set_footer(text=BOT_FOOTER)
    embed.timestamp = dt.datetime.now(dt.timezone.utc)
    return embed


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
        value="**tmate SSH**\n`root user`",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['spark']} Plan",
        value=f"`{PLAN['name']}` • Location: `{PLAN['location']}`",
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


def deploy_success_embed(info: dict, ssh: str | None) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJI['check']} VPS deployed successfully!",
        description=(
            "Your free VPS is **online** and ready to use.\n"
            f"Manage it any time with `!manage`."
        ),
        color=COLOR_SUCCESS,
    )
    embed.add_field(name="Server ID", value=f"`{info['short_id']}`", inline=True)
    embed.add_field(name="Hostname", value=f"`{info['name']}`", inline=True)
    embed.add_field(name="Status", value=status_badge(info["status"]), inline=True)

    embed.add_field(
        name=f"{EMOJI['ram']} RAM",
        value=f"**{info['ram_limit_mb']} MB**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['cpu']} vCPU",
        value=f"**{info['cpu_limit']:g}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['disk']} Disk",
        value=f"**{info['disk_gb']} GB**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['os']} OS",
        value=f"**{info['os']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['net']} Bandwidth",
        value=f"**{info['bandwidth']}**",
        inline=True,
    )
    embed.add_field(
        name=f"{EMOJI['clock']} Created",
        value=f"<t:{int(info['created_ts'])}:R>",
        inline=True,
    )

    if ssh:
        embed.add_field(
            name=f"{EMOJI['key']} SSH access (tmate)",
            value=f"```bash\n{ssh}\n```Paste this in your terminal to connect as `root`.",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{EMOJI['key']} SSH access (tmate)",
            value="Session is still starting. Run `!manage` → **Get SSH** in a moment.",
            inline=False,
        )
    return _footer(embed)


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
def manage_embed(info: dict, ssh: str | None = None) -> discord.Embed:
    running = info["status"] == "running"
    embed = discord.Embed(
        title=f"{EMOJI['gear']} VPS Control Panel",
        description=(
            f"**{info['name']}** • {status_badge(info['status'])}\n"
            f"Use the buttons below to control your server."
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
    embed.add_field(
        name="Created", value=f"<t:{int(info['created_ts'])}:D>", inline=True
    )

    if ssh:
        embed.add_field(
            name=f"{EMOJI['key']} SSH access (tmate)",
            value=f"```bash\n{ssh}\n```",
            inline=False,
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
            description=description,
            color=COLOR_ERROR,
        )
    )


def help_embed(prefix: str) -> discord.Embed:
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
        name=f"`{prefix}ping`",
        value="Check bot latency.",
        inline=False,
    )
    return _footer(embed)
