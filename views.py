"""Interactive buttons (discord.ui) for Cloudy VPS Bot.

Security: SSH credentials are only ever delivered by direct message (with an
ephemeral fallback when DMs are closed). They are never posted in a channel.

Every view carries a `lang` ("en" / "ru") so labels and messages match the
language the user picked with `!lang`.
"""

from __future__ import annotations

import asyncio
import logging

import discord

import embeds
from config import (
    ANIM_DELAY,
    COLOR_PRIMARY,
    COMMAND_PREFIX,
    EMOJI,
    SSH_TO_DM_ONLY,
    is_owner,
)
from i18n import DEFAULT_LANG, LANGUAGES, LangStore, t
from maintenance import MAINTENANCE, MaintenanceStore
from moderation import BanStore
from slots import MAX_SLOTS, MIN_SLOTS, SLOTS, SlotStore
from vps_manager import VPSError, VPSManager

log = logging.getLogger("cloudy.views")


async def deliver_ssh(
    user: discord.abc.User,
    info: dict,
    ssh: str,
    interaction: discord.Interaction | None = None,
    lang: str = DEFAULT_LANG,
) -> bool:
    """Send the SSH command privately. Returns True if the DM was delivered."""
    embed = embeds.ssh_dm_embed(info, ssh, lang)
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("DM to %s failed: %s", user.id, exc)

    if interaction is not None:
        # Ephemeral fallback: still private, only this user can read it.
        target = interaction.followup if interaction.response.is_done() else interaction.response
        try:
            if not SSH_TO_DM_ONLY:
                await target.send(embed=embed, ephemeral=True)
            else:
                await target.send(embed=embeds.dm_failed_embed(lang), ephemeral=True)
                await target.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass
    return False


class OwnerOnlyView(discord.ui.View):
    """Base view that only reacts to the user who ran the command."""

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        timeout: float | None = 300,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.owner_id = owner_id
        self.bans = bans
        self.lang = lang
        self.message: discord.Message | None = None
        self.localize_labels()

    # Button labels are class-level in discord.py, so translate them per instance.
    LABEL_KEYS: dict[str, str] = {}

    def localize_labels(self) -> None:
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            key = self.LABEL_KEYS.get(child.custom_id or "") or self.LABEL_KEYS.get(
                (child.label or "").lower()
            )
            if key:
                child.label = t(self.lang, key)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "panel.not_yours"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return False
        if self.bans is not None and self.bans.is_banned(interaction.user.id):
            record = self.bans.get(interaction.user.id) or {}
            await interaction.response.send_message(
                embed=embeds.banned_notice_embed(record, self.lang), ephemeral=True
            )
            return False
        # Maintenance mode: buttons are frozen for everyone except staff.
        if MAINTENANCE.enabled and not is_owner(interaction.user.id):
            await interaction.response.send_message(
                embed=embeds.maintenance_embed(MAINTENANCE.state(), self.lang),
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
# (stage key, percent, ansi log line)
DEPLOY_STAGES: list[tuple[str, int, str]] = [
    ("stage.alloc", 8, "\u001b[0;36m[cloudy]\u001b[0m reserving 1 vCPU / RAM slice"),
    ("stage.image", 22, "\u001b[0;36m[image]\u001b[0m ubuntu:22.04 \u2192 ok"),
    ("stage.disk", 36, "\u001b[0;36m[disk]\u001b[0m formatting 10 GB volume"),
    ("stage.boot", 52, "\u001b[0;36m[boot]\u001b[0m kernel handoff \u2192 init"),
    ("stage.net", 66, "\u001b[0;36m[net]\u001b[0m bridge attached, DNS ready"),
    ("stage.apt", 78, "\u001b[0;36m[apt]\u001b[0m curl git htop python3 tmux"),
    ("stage.tmate", 90, "\u001b[0;36m[tmate]\u001b[0m negotiating secure tunnel"),
    ("stage.health", 97, "\u001b[0;32m[ok]\u001b[0m all services healthy"),
]


class DeployView(OwnerOnlyView):
    LABEL_KEYS = {"start": "btn.start", "rules": "btn.rules", "cancel": "btn.cancel"}

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(manager, owner_id, bans, timeout=180, lang=lang)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="\U0001F680")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = self.lang
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.deploy_progress_embed(t(lang, "progress.init"), 3, [], lang),
            view=self,
        )
        message = interaction.message

        # Real work runs in the background while the animation plays.
        task = asyncio.create_task(
            self.manager.create_vps(interaction.user.id, str(interaction.user), lang)
        )

        log_lines: list[str] = []
        try:
            for stage_key, percent, line in DEPLOY_STAGES:
                log_lines.append(line)
                await message.edit(
                    embed=embeds.deploy_progress_embed(
                        t(lang, stage_key), percent, log_lines, lang
                    ),
                    view=self,
                )
                await asyncio.sleep(ANIM_DELAY)
            await task
        except VPSError as exc:
            await message.edit(embed=embeds.error_embed(str(exc), lang=lang), view=None)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("deploy failed")
            await message.edit(
                embed=embeds.error_embed(
                    t(lang, "deploy.failed", error=exc), lang=lang
                ),
                view=None,
            )
            return

        info = await self.manager.get_info(interaction.user.id)

        # tmate session + private delivery
        ssh_status = ""
        try:
            ssh = await self.manager.get_ssh(interaction.user.id)
            sent = await deliver_ssh(interaction.user, info, ssh, interaction, lang)
            ssh_status = (
                f"{EMOJI['mail']} {t(lang, 'ssh.sent_dm')}"
                if sent
                else f"{EMOJI['lock']} {t(lang, 'ssh.sent_ephemeral')}"
            )
        except asyncio.TimeoutError:
            ssh_status = t(lang, "ssh.slow")
        except VPSError as exc:
            log.warning("tmate not ready: %s", exc)
            ssh_status = t(lang, "ssh.retry")
            try:
                await interaction.followup.send(
                    embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
                )
            except discord.HTTPException:
                pass

        await message.edit(
            embed=embeds.deploy_progress_embed(
                t(lang, "progress.finishing"), 100, log_lines, lang
            ),
            view=self,
        )
        await asyncio.sleep(0.6)

        manage_view = ManageView(self.manager, interaction.user.id, self.bans, lang=lang)
        await manage_view.refresh_buttons(info)
        await message.edit(
            embed=embeds.deploy_success_embed(info, ssh_status, lang), view=manage_view
        )
        manage_view.message = message
        self.stop()

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.primary, emoji="\U0001F4DC")
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embeds.rules_embed(self.lang), ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="\u2716\ufe0f")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.info_embed(
                f"{EMOJI['cloud']} {t(self.lang, 'cancel.title')}",
                t(self.lang, "cancel.desc", prefix=COMMAND_PREFIX),
                COLOR_PRIMARY,
            ),
            view=None,
        )
        self.stop()


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
class ManageView(OwnerOnlyView):
    LABEL_KEYS = {
        "vps_start": "btn.start",
        "vps_stop": "btn.stop",
        "vps_restart": "btn.restart",
        "vps_ssh": "btn.ssh",
        "vps_refresh": "btn.refresh",
        "vps_rules": "btn.rules",
    }

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(manager, owner_id, bans, timeout=600, lang=lang)

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

    async def _do(self, interaction: discord.Interaction, action: str, verb_key: str):
        lang = self.lang
        await interaction.response.defer()
        try:
            await self.manager.power_action(interaction.user.id, action)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return
        except Exception as exc:  # pragma: no cover
            log.exception("%s failed", action)
            await interaction.followup.send(
                embed=embeds.error_embed(f"`{exc}`", lang=lang), ephemeral=True
            )
            return

        await asyncio.sleep(1.5)  # let the container settle before reading stats
        info = await self.manager.get_info(interaction.user.id)
        await self.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, lang), view=self
        )
        await interaction.followup.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} {t(lang, verb_key)}",
                t(lang, "manage.now_status", name=info["name"], status=info["status"])
                + (
                    t(lang, "manage.session_closed")
                    if action in ("stop", "restart")
                    else ""
                ),
                COLOR_PRIMARY,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Start", style=discord.ButtonStyle.success, emoji="\u25B6\ufe0f", custom_id="vps_start"
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "start", "manage.started")

    @discord.ui.button(
        label="Stop", style=discord.ButtonStyle.danger, emoji="\u23F9\ufe0f", custom_id="vps_stop"
    )
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "stop", "manage.stopped")

    @discord.ui.button(
        label="Restart",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F504",
        custom_id="vps_restart",
    )
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "restart", "manage.restarted")

    @discord.ui.button(
        label="Get SSH",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F511",
        custom_id="vps_ssh",
        row=1,
    )
    async def ssh(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            ssh = await self.manager.get_ssh(interaction.user.id, force_new=True)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=embeds.error_embed(t(lang, "ssh.timeout"), lang=lang),
                ephemeral=True,
            )
            return
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return

        info = await self.manager.get_info(interaction.user.id)
        sent = await deliver_ssh(interaction.user, info, ssh, interaction, lang)
        if sent:
            await interaction.followup.send(
                embed=embeds.info_embed(
                    f"{EMOJI['mail']} {t(lang, 'ssh.check_dms_title')}",
                    t(lang, "ssh.check_dms_desc"),
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
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=self.lang), ephemeral=True
            )
            return
        await self.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, self.lang), view=self
        )

    @discord.ui.button(
        label="Rules",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F4DC",
        custom_id="vps_rules",
        row=1,
    )
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embeds.rules_embed(self.lang), ephemeral=True
        )


# ---------------------------------------------------------------------------
# !lang - language picker
# ---------------------------------------------------------------------------
class LanguageSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(
                label=meta["name"],
                value=code,
                emoji=meta["flag"],
                default=(code == current),
                description={"ru": "\u0418\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441 \u0431\u043e\u0442\u0430 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c", "en": "Bot interface in English"}[code],
            )
            for code, meta in LANGUAGES.items()
        ]
        super().__init__(
            placeholder=t(current, "lang.select_placeholder"),
            min_values=1,
            max_values=1,
            options=options,
            custom_id="lang_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LanguageView = self.view  # type: ignore[assignment]
        new_lang = view.store.set(interaction.user.id, self.values[0])
        view.lang = new_lang
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.language_changed_embed(new_lang), view=view
        )
        view.stop()


class LanguageView(discord.ui.View):
    """Small select menu so the user can pick Russian or English."""

    def __init__(self, owner_id: int, store: LangStore, current: str = DEFAULT_LANG):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.store = store
        self.lang = current
        self.message: discord.Message | None = None
        self.add_item(LanguageSelect(current))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "panel.not_yours"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
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
# !admin - staff panel with the maintenance switch
# ---------------------------------------------------------------------------
class AdminView(discord.ui.View):
    """Owner-only panel: turn maintenance mode on/off and see live counters."""

    def __init__(
        self,
        owner_id: int,
        maintenance: MaintenanceStore = MAINTENANCE,
        manager: VPSManager | None = None,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
        slots: SlotStore = SLOTS,
    ):
        super().__init__(timeout=600)
        self.owner_id = owner_id
        self.maintenance = maintenance
        self.manager = manager
        self.bans = bans
        self.lang = lang
        self.slots = slots
        self.stats: dict = {}
        self.message: discord.Message | None = None
        self.sync_buttons()

    # ---- helpers ----
    def _counts(self) -> tuple[int, int]:
        servers = 0
        if self.manager is not None:
            try:
                servers = len(self.manager.all_records())
            except Exception:  # pragma: no cover
                servers = 0
        ban_count = self.bans.count if self.bans is not None else 0
        return servers, ban_count

    async def refresh_stats(self) -> dict:
        """Live running / stopped / slot counters from Docker."""
        if self.manager is not None:
            try:
                self.stats = await self.manager.stats()
            except Exception as exc:  # pragma: no cover
                log.warning("could not read VPS stats: %s", exc)
                self.stats = {}
        return self.stats

    def panel_embed(self) -> discord.Embed:
        servers, ban_count = self._counts()
        return embeds.admin_panel_embed(
            self.maintenance.state(),
            servers,
            ban_count,
            self.lang,
            stats=self.stats or None,
        )

    async def build_embed(self) -> discord.Embed:
        """Panel embed with fresh counters (use this instead of panel_embed)."""
        await self.refresh_stats()
        return self.panel_embed()

    def sync_buttons(self) -> None:
        on = self.maintenance.enabled
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "maint_toggle":
                child.label = t(self.lang, "admin.btn_off" if on else "admin.btn_on")
                child.style = (
                    discord.ButtonStyle.success if on else discord.ButtonStyle.danger
                )
                child.emoji = "\u2705" if on else "\U0001F6A7"
            elif child.custom_id == "maint_preview":
                child.label = t(self.lang, "admin.btn_preview")
            elif child.custom_id == "maint_refresh":
                child.label = t(self.lang, "admin.btn_refresh")
            elif child.custom_id == "slot_plus":
                child.label = t(self.lang, "admin.btn_slot_plus")
                child.disabled = self.slots.total >= MAX_SLOTS
            elif child.custom_id == "slot_minus":
                child.label = t(self.lang, "admin.btn_slot_minus")
                child.disabled = self.slots.total <= MIN_SLOTS

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not is_owner(interaction.user.id):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "admin.only_staff"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
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

    # ---- buttons ----
    @discord.ui.button(
        label="Maintenance",
        style=discord.ButtonStyle.danger,
        emoji="\U0001F6A7",
        custom_id="maint_toggle",
    )
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self.maintenance.toggle(
            interaction.user.id, str(interaction.user)
        )
        await interaction.response.defer()
        embed = await self.build_embed()
        self.sync_buttons()
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.followup.send(
            embed=embeds.maintenance_toggled_embed(state, self.lang), ephemeral=True
        )

    @discord.ui.button(
        label="Preview",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F441\ufe0f",
        custom_id="maint_preview",
    )
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show exactly what regular users see while maintenance is on."""
        await interaction.response.send_message(
            embed=embeds.maintenance_embed(self.maintenance.state(), self.lang),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F501",
        custom_id="maint_refresh",
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await self.build_embed()
        self.sync_buttons()
        await interaction.edit_original_response(embed=embed, view=self)

    # ---- capacity buttons ----
    async def _change_slots(self, interaction: discord.Interaction, delta: int) -> None:
        old = self.slots.total
        await self.slots.add(delta, interaction.user.id, str(interaction.user))
        await interaction.response.defer()
        embed = await self.build_embed()
        self.sync_buttons()
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.followup.send(
            embed=embeds.slots_changed_embed(old, self.stats, self.lang),
            ephemeral=True,
        )

    @discord.ui.button(
        label="-1 slot",
        style=discord.ButtonStyle.secondary,
        emoji="\u2796",
        custom_id="slot_minus",
        row=1,
    )
    async def slot_minus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_slots(interaction, -1)

    @discord.ui.button(
        label="+1 slot",
        style=discord.ButtonStyle.success,
        emoji="\u2795",
        custom_id="slot_plus",
        row=1,
    )
    async def slot_plus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_slots(interaction, +1)
