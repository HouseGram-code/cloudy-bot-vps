"""Cloudy VPS Bot - free VPS hosting from Discord.

Version 1.0 Beta
"""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

import embeds
from config import (
    BOT_NAME,
    BOT_VERSION,
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    EMOJI,
    OWNER_IDS,
    RULES,
    is_owner,
)
from moderation import BanStore, ModerationError
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
bans = BanStore()


class Banned(commands.CheckFailure):
    pass


@bot.event
async def on_ready() -> None:
    global manager
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    log.info("%s v%s ready | owners: %s | bans: %d", BOT_NAME, BOT_VERSION, OWNER_IDS, bans.count)
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


@bot.check
async def _block_banned(ctx: commands.Context) -> bool:
    if bans.is_banned(ctx.author.id):
        raise Banned()
    return True


async def _resolve_user_id(ctx: commands.Context, raw: str) -> tuple[int, str]:
    """Accept a mention, a raw ID, or a name and return (id, display name)."""
    match = re.search(r"\d{15,25}", raw or "")
    if match:
        uid = int(match.group(0))
        user = bot.get_user(uid)
        if user is None:
            try:
                user = await bot.fetch_user(uid)
            except discord.HTTPException:
                user = None
        return uid, (str(user) if user else f"User {uid}")

    try:
        member = await commands.MemberConverter().convert(ctx, raw)
        return member.id, str(member)
    except commands.BadArgument as exc:
        raise ModerationError(
            "Could not find that user. Use a mention or a numeric ID, for example "
            f"`{COMMAND_PREFIX}ban 1264586393594630239 spam`."
        ) from exc


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------
@bot.command(name="deploy")
@commands.cooldown(1, 15, commands.BucketType.user)
async def deploy(ctx: commands.Context) -> None:
    """Show the free plan specs and deploy a VPS."""
    try:
        mgr = _require_manager()
        if await mgr.has_vps(ctx.author.id):
            info = await mgr.get_info(ctx.author.id)
            view = ManageView(mgr, ctx.author.id, bans)
            await view.refresh_buttons(info)
            msg = await ctx.reply(
                content=f"{EMOJI['cloud']} You already own a VPS — here is your control panel.",
                embed=embeds.manage_embed(info),
                view=view,
                mention_author=False,
            )
            view.message = msg
            return
    except VPSError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    view = DeployView(mgr, ctx.author.id, bans)
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

    view = ManageView(mgr, ctx.author.id, bans)
    await view.refresh_buttons(info)
    msg = await ctx.reply(embed=embeds.manage_embed(info), view=view, mention_author=False)
    view.message = msg


@bot.command(name="rules")
async def rules_cmd(ctx: commands.Context) -> None:
    await ctx.reply(embed=embeds.rules_embed(), mention_author=False)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    await ctx.reply(
        embed=embeds.help_embed(COMMAND_PREFIX, owner=is_owner(ctx.author.id)),
        mention_author=False,
    )


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
# Staff commands (owners only)
# ---------------------------------------------------------------------------
def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_owner(ctx.author.id):
            raise commands.CheckFailure("staff_only")
        return True

    return commands.check(predicate)


@bot.command(name="ban")
@owner_only()
async def ban_cmd(ctx: commands.Context, target: str = "", *, reason: str = "") -> None:
    """!ban <@user|id> [reason] - block a user and stop their server."""
    if not target:
        await ctx.reply(
            embed=embeds.error_embed(
                f"Usage: `{COMMAND_PREFIX}ban <@user|id> [reason]`", title="Missing user"
            ),
            mention_author=False,
        )
        return

    try:
        user_id, user_name = await _resolve_user_id(ctx, target)
        record = await bans.ban(
            user_id=user_id,
            reason=reason.strip(),
            moderator_id=ctx.author.id,
            moderator_name=str(ctx.author),
            user_name=user_name,
        )
    except ModerationError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    stopped = False
    if manager is not None:
        try:
            stopped = await manager.stop_if_running(user_id)
        except Exception as exc:  # pragma: no cover
            log.warning("could not stop server of %s: %s", user_id, exc)

    # Tell the user privately why they lost access.
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(embed=embeds.banned_notice_embed(record))
    except discord.HTTPException:
        pass

    await ctx.reply(embed=embeds.ban_embed(record, stopped), mention_author=False)


@bot.command(name="unban")
@owner_only()
async def unban_cmd(ctx: commands.Context, target: str = "") -> None:
    """!unban <@user|id> - restore access."""
    if not target:
        await ctx.reply(
            embed=embeds.error_embed(
                f"Usage: `{COMMAND_PREFIX}unban <@user|id>`", title="Missing user"
            ),
            mention_author=False,
        )
        return

    try:
        user_id, _ = await _resolve_user_id(ctx, target)
        record = await bans.unban(user_id)
    except ModerationError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} You were unbanned",
                f"You can use **{BOT_NAME}** again. Please follow the "
                f"{len(RULES)} rules (`{COMMAND_PREFIX}rules`).",
            )
        )
    except discord.HTTPException:
        pass

    await ctx.reply(embed=embeds.unban_embed(record), mention_author=False)


@bot.command(name="bans")
@owner_only()
async def bans_cmd(ctx: commands.Context) -> None:
    await ctx.reply(embed=embeds.bans_list_embed(bans.all_bans()), mention_author=False)


@bot.command(name="servers")
@owner_only()
async def servers_cmd(ctx: commands.Context) -> None:
    try:
        mgr = _require_manager()
    except VPSError as exc:
        await ctx.reply(embed=embeds.error_embed(str(exc)), mention_author=False)
        return

    records = mgr.all_records()
    if not records:
        await ctx.reply(
            embed=embeds.info_embed(f"{EMOJI['cloud']} Servers", "No servers deployed yet."),
            mention_author=False,
        )
        return

    lines = [
        f"`{r['name']}` • <@{r['owner_id']}> • {r['ram_mb']} MB • "
        f"<t:{int(r['created_ts'])}:R>"
        for r in records[:25]
    ]
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['cloud']} Servers ({len(records)})", "\n".join(lines)
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

    if isinstance(error, Banned):
        record = bans.get(ctx.author.id) or {}
        try:
            await ctx.author.send(embed=embeds.banned_notice_embed(record))
        except discord.HTTPException:
            await ctx.reply(
                embed=embeds.error_embed(
                    "You are banned from using this bot.", title="Access denied"
                ),
                mention_author=False,
            )
        return

    if isinstance(error, commands.CheckFailure):
        await ctx.reply(
            embed=embeds.error_embed(
                "This command is for bot staff only.", title="Access denied"
            ),
            mention_author=False,
        )
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
    await ctx.reply(embed=embeds.error_embed(f"`{error}`"), mention_author=False)


def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set.")
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
