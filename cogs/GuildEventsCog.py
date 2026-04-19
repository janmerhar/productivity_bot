import discord
from discord.ext import commands

from embeds.SettingsEmbeds import SettingsEmbeds


class GuildEventsCog(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("GuildEventsCog cog loaded")

    async def _find_inviter(self, guild: discord.Guild) -> discord.Member | None:
        try:
            async for entry in guild.audit_logs(
                action=discord.AuditLogAction.bot_add, limit=5
            ):
                if entry.target.id == self.client.user.id:
                    return entry.user
        except discord.Forbidden:
            pass
        return guild.owner

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        channel = guild.system_channel
        if channel is None:
            channel = next(
                (
                    c
                    for c in guild.text_channels
                    if c.permissions_for(guild.me).send_messages
                ),
                None,
            )
        if channel is not None:
            await channel.send(embed=SettingsEmbeds.info_embed())

        inviter = await self._find_inviter(guild)
        if inviter is None:
            return
        try:
            await inviter.send(embed=SettingsEmbeds.info_embed())
        except discord.Forbidden:
            pass


async def setup(client: commands.Bot) -> None:
    await client.add_cog(GuildEventsCog(client))
