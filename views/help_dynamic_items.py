from typing import Optional

import discord
from discord.ext import commands


async def register_help_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(HelpCategorySelect)


class HelpCategorySelect(
    discord.ui.DynamicItem[discord.ui.Select],
    template=r"help:category",
):
    def __init__(
        self,
        current_value: str,
        *,
        select: Optional[discord.ui.Select] = None,
    ) -> None:
        from views.HelpView import _CATEGORY_OPTIONS

        if select is None:
            options = [
                discord.SelectOption(
                    label=option.label,
                    value=option.value,
                    description=option.description,
                    emoji=option.emoji,
                    default=option.value == current_value,
                )
                for option in _CATEGORY_OPTIONS
            ]
            select = discord.ui.Select(
                placeholder="Browse a category...",
                min_values=1,
                max_values=1,
                options=options,
                custom_id="help:category",
            )

        super().__init__(select)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HelpCategorySelect":
        del interaction, match
        if not isinstance(item, discord.ui.Select):
            raise TypeError("Help categories must use a select component.")
        return cls("", select=item)

    async def callback(self, interaction: discord.Interaction) -> None:
        from embeds.SettingsEmbeds import SettingsEmbeds
        from views.HelpView import HelpView, _EMBED_FOR_CATEGORY

        values = self.item.values
        selected = values[0] if values else "quick_start"
        builder = _EMBED_FOR_CATEGORY.get(
            selected,
            SettingsEmbeds.help_welcome_embed,
        )
        await interaction.response.edit_message(
            embed=builder(),
            view=HelpView(category=selected),
        )
