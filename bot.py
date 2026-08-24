"""Cloudy VPS Bot - free VPS hosting from Discord.

Version 1.0 Beta
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import embeds
from config import (
    BOT_NAME,
    BOT_VERSION,
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    EMOJI,
)
from views import DeployView, ManageView
from vps_manager import VPSError, VPSManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("cloudy.bot")

intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=None,
    activity=discord.Game(name=f"{COMMAND_PREFIX}deploy \u2022 free VPS"),
)

manager: VPSManager | None = None


@bot.event
async def on_ready() -> None:
    global manager
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    log.info("%s v%s ready", BOT_NAME, BOT_VERSION)
    if manager is None:
        try:
            manager = VPSManager()
            await manager.ensure_image()
            log.info("Docker backend ready, VPS image available")
        except Exception as exc:
            log.error("Docker backend unavailable: %s", exc)


def _require_manager() -> VPSManager:
    if manager is None:
        raise VPSError(
            "The Docker backend is not available. Check the bot logs and make sure "
            "`/var/run/docker.sock` is mounted."
        )
    return manager


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@bot.command(name="deploy")
@commands.cooldown(1, 15, commands.BucketType.user)
async def deploy(ctx: commands.Context) -> None:
    """Show the free plan specs and deploy a VPS."""
    try:
        mgr = _require_manager()
        if await mgr.has_vps(ctx.author.id):
            info = await mgr.get_info(ctx.author.id)
            view = ManageView(mgr, ctx.author.id)
            await view.refresh_buttons(info)
            msg = await ctx.reply(
                content=(
                    f"{EMOJI['cloud']} You already own a VPS — here is your control panel."
                ),
                embed=embeds.manage_embed(info),
                view=view,
                mention_author=False,
            )
            view.message = msg
            return
    except VPSError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    view = DeployView(mgr, ctx.author.id)
    msg = await ctx.reply(
        embed=embeds.deploy_offer_embed(ctx.author), view=view, mention_author=False
    )
    view.message = msg


@bot.command(name="manage")
@commands.cooldown(1, 5, commands.BucketType.user)
async def manage(ctx: commands.Context) -> None:
    """Server info + power controls."""
    try:
        mgr = _require_manager()
        info = await mgr.get_info(ctx.author.id)
    except VPSError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    view = ManageView(mgr, ctx.author.id)
    await view.refresh_buttons(info)
    msg = await ctx.reply(
        embed=embeds.manage_embed(info, ssh=info.get("ssh")),
        view=view,
        mention_author=False,
    )
    view.message = msg


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    await ctx.reply(embed=embeds.help_embed(COMMAND_PREFIX), mention_author=False)


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['spark']} Pong!",
            f"Gateway latency: **{round(bot.latency * 1000)} ms**",
        ),
        mention_author=False,
    )


@bot.command(name="destroy")
@commands.cooldown(1, 30, commands.BucketType.user)
async def destroy(ctx: commands.Context) -> None:
    """Permanently delete your VPS."""
    try:
        mgr = _require_manager()
        await mgr.delete_vps(ctx.author.id)
    except VPSError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['check']} VPS destroyed",
            "Your server and its disk were removed. You can `!deploy` a new one.",
        ),
        mention_author=False,
    )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(
            embed=embeds.error_embed(
                f"Slow down — try again in **{error.retry_after:.0f}s**.",
                title="On cooldown",
            ),
            mention_author=False,
        )
        return
    log.exception("command error", exc_info=error)
    await ctx.reply(
        embed=embeds.error_embed(f"`{error}`"), mention_author=False
    )


def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env first.")
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
