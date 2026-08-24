"""Interactive buttons (discord.ui) for Cloudy VPS Bot."""

from __future__ import annotations

import asyncio
import logging

import discord

import embeds
from config import ANIM_DELAY, COLOR_PRIMARY, EMOJI
from vps_manager import VPSError, VPSManager

log = logging.getLogger("cloudy.views")


class OwnerOnlyView(discord.ui.View):
    """Base view that only reacts to the user who ran the command."""

    def __init__(self, manager: VPSManager, owner_id: int, timeout: float | None = 300):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.owner_id = owner_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "This panel belongs to someone else. Run the command yourself to get your own.",
                    title="Not your panel",
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# !deploy
# ---------------------------------------------------------------------------
DEPLOY_STAGES: list[tuple[str, int, str]] = [
    ("Allocating resources…", 8, "\u001b[0;36m[cloudy]\u001b[0m reserving 1 vCPU / RAM slice"),
    ("Pulling Ubuntu 22.04 LTS image…", 22, "\u001b[0;36m[image]\u001b[0m ubuntu:22.04 \u2192 ok"),
    ("Creating virtual disk…", 36, "\u001b[0;36m[disk]\u001b[0m formatting 10 GB volume"),
    ("Booting the machine…", 52, "\u001b[0;36m[boot]\u001b[0m kernel handoff \u2192 systemd-less init"),
    ("Configuring network…", 66, "\u001b[0;36m[net]\u001b[0m bridge attached, DNS ready"),
    ("Installing base packages…", 78, "\u001b[0;36m[apt]\u001b[0m curl git htop python3 tmux"),
    ("Starting tmate SSH session…", 90, "\u001b[0;36m[tmate]\u001b[0m negotiating secure tunnel"),
    ("Running final health checks…", 97, "\u001b[0;32m[ok]\u001b[0m all services healthy"),
]


class DeployView(OwnerOnlyView):
    def __init__(self, manager: VPSManager, owner_id: int):
        super().__init__(manager, owner_id, timeout=180)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="\U0001F680")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.deploy_progress_embed("Initializing…", 3, []),
            view=self,
        )
        message = interaction.message

        # Real work runs in the background while the animation plays.
        task = asyncio.create_task(
            self.manager.create_vps(interaction.user.id, str(interaction.user))
        )

        log_lines: list[str] = []
        try:
            for label, percent, line in DEPLOY_STAGES:
                log_lines.append(line)
                await message.edit(
                    embed=embeds.deploy_progress_embed(label, percent, log_lines),
                    view=self,
                )
                await asyncio.sleep(ANIM_DELAY)

            record = await task
        except VPSError as exc:
            await message.edit(embed=embeds.error_embed(str(exc)), view=None)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("deploy failed")
            await message.edit(
                embed=embeds.error_embed(f"Deployment failed: `{exc}`"), view=None
            )
            return

        # Fetch live info + tmate SSH.
        info = await self.manager.get_info(interaction.user.id)
        ssh = None
        try:
            ssh = await self.manager.get_ssh(interaction.user.id)
        except (VPSError, asyncio.TimeoutError) as exc:
            log.warning("tmate not ready: %s", exc)

        await message.edit(
            embed=embeds.deploy_progress_embed("Finishing up…", 100, log_lines),
            view=self,
        )
        await asyncio.sleep(0.6)

        manage_view = ManageView(self.manager, interaction.user.id)
        await manage_view.refresh_buttons(info)
        await message.edit(embed=embeds.deploy_success_embed(info, ssh), view=manage_view)
        manage_view.message = message
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="\u2716\ufe0f")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.info_embed(
                f"{EMOJI['cloud']} Deployment cancelled",
                "No server was created. Run `!deploy` whenever you are ready.",
                COLOR_PRIMARY,
            ),
            view=None,
        )
        self.stop()


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
class ManageView(OwnerOnlyView):
    def __init__(self, manager: VPSManager, owner_id: int):
        super().__init__(manager, owner_id, timeout=600)

    async def refresh_buttons(self, info: dict) -> None:
        running = info["status"] == "running"
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "vps_start":
                child.disabled = running
            elif child.custom_id in ("vps_stop", "vps_restart", "vps_ssh"):
                child.disabled = not running
            else:
                child.disabled = False

    async def _do(self, interaction: discord.Interaction, action: str, verb: str):
        await interaction.response.defer()
        try:
            await self.manager.power_action(interaction.user.id, action)
        except VPSError as exc:
            await interaction.followup.send(embed=embeds.error_embed(str(exc)), ephemeral=True)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("%s failed", action)
            await interaction.followup.send(
                embed=embeds.error_embed(f"`{exc}`"), ephemeral=True
            )
            return

        await asyncio.sleep(1.5)  # let the container settle before reading stats
        info = await self.manager.get_info(interaction.user.id)
        await self.refresh_buttons(info)
        await interaction.edit_original_response(embed=embeds.manage_embed(info), view=self)
        await interaction.followup.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} {verb}",
                f"Your VPS `{info['name']}` is now **{info['status']}**.",
                COLOR_PRIMARY,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Start", style=discord.ButtonStyle.success, emoji="\u25B6\ufe0f", custom_id="vps_start"
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "start", "Server started")

    @discord.ui.button(
        label="Stop", style=discord.ButtonStyle.danger, emoji="\u23F9\ufe0f", custom_id="vps_stop"
    )
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "stop", "Server stopped")

    @discord.ui.button(
        label="Restart",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F504",
        custom_id="vps_restart",
    )
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "restart", "Server restarted")

    @discord.ui.button(
        label="Get SSH",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F511",
        custom_id="vps_ssh",
        row=1,
    )
    async def ssh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            ssh = await self.manager.get_ssh(interaction.user.id, force_new=True)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=embeds.error_embed("tmate took too long to respond. Try again."),
                ephemeral=True,
            )
            return
        except VPSError as exc:
            await interaction.followup.send(embed=embeds.error_embed(str(exc)), ephemeral=True)
            return

        await interaction.followup.send(
            embed=embeds.info_embed(
                f"{EMOJI['key']} tmate SSH access",
                f"Connect to **your VPS** with:\n```bash\n{ssh}\n```"
                "\nThis session stays alive while the server is running.",
                COLOR_PRIMARY,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F501",
        custom_id="vps_refresh",
        row=1,
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            info = await self.manager.get_info(interaction.user.id)
        except VPSError as exc:
            await interaction.followup.send(embed=embeds.error_embed(str(exc)), ephemeral=True)
            return
        await self.refresh_buttons(info)
        await interaction.edit_original_response(embed=embeds.manage_embed(info), view=self)
