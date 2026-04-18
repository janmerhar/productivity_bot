import asyncio
from typing import Optional

import discord

from classes.BugReportFunctions import BugReportFunctions
from embeds.BugReportEmbeds import BugReportEmbeds
from services.error_reporting import UserVisibleError, ValidationError, handle_interaction_error


class BugReportModal(discord.ui.Modal, title="Bug Report"):
    bug = discord.ui.TextInput(
        label="Bug Description",
        placeholder="Describe what went wrong",
        required=True,
        max_length=2000,
        style=discord.TextStyle.paragraph,
    )
    link = discord.ui.TextInput(
        label="Link",
        placeholder="Optional link with more context (screenshots, message link, etc.)",
        required=False,
        max_length=500,
    )

    def __init__(
        self,
        *,
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        ephemeral: bool,
    ) -> None:
        super().__init__()
        self._guild_id = guild_id
        self._user_id = user_id
        self._channel_id = channel_id
        self._ephemeral = ephemeral

        self.attachment = discord.ui.FileUpload(required=False, max_values=1)
        self.attachment_label = discord.ui.Label(
            text="Attachment",
            component=self.attachment,
        )
        self.add_item(self.attachment_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_bug = str(self.bug.value or "").strip()
        raw_link = str(self.link.value or "").strip() or None
        attachments = self.attachment.values
        raw_attachment_url = attachments[0].url if attachments else None

        if not raw_bug:
            await interaction.response.send_message(
                "Bug report cannot be empty.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=self._ephemeral)

        try:
            document = await asyncio.to_thread(
                BugReportFunctions.insert_bug_report,
                self._guild_id,
                self._user_id,
                self._channel_id,
                raw_bug,
                raw_link,
                raw_attachment_url,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=self._ephemeral, cause=exc),
                ephemeral=self._ephemeral,
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while saving that bug report.",
                    ephemeral=self._ephemeral,
                    cause=exc,
                ),
                ephemeral=self._ephemeral,
            )
            return

        payload = BugReportEmbeds.received_embed(document)
        await interaction.followup.send(ephemeral=self._ephemeral, **payload)
