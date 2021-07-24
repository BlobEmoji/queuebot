import asyncio

import discord
from discord import ui
from discord.ext import commands


class ConfirmationView(ui.View):
    def __init__(self, owner: discord.User):
        super().__init__(timeout=60)

        self.owner: discord.User = owner
        self.message: discord.Message = None
        self.result: asyncio.Future = asyncio.get_event_loop().create_future()

    async def interaction_check(self, interaction: discord.Interaction):
        return not self.owner or interaction.user.id == self.owner.id

    async def on_timeout(self):
        if not self.result.done():
            self.result.set_exception(asyncio.TimeoutError())

        if self.message:
            await self.message.edit(view=None)

    @ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def button_yes(self, button: ui.Button, interaction: discord.Interaction):
        if not self.result.done():
            self.result.set_result(True)

        await interaction.response.edit_message(view=None)
        self.stop()

    @ui.button(label="No", style=discord.ButtonStyle.red)
    async def button_no(self, button: ui.Button, interaction: discord.Interaction):
        if not self.result.done():
            self.result.set_result(False)

        await interaction.response.edit_message(view=None)
        self.stop()


class Context(commands.Context):
    async def confirm(self, description=None, *, embed=None, title=None, color=None):
        embed = embed if embed is not None else discord.Embed()

        embed.color = color or discord.Colour.red()
        embed.title = title or 'Are you sure?'
        embed.set_footer(text=str(self.author), icon_url=str(self.author.avatar))
        embed.description = description

        view = ConfirmationView(self.author)
        view.message = await self.send(embed=embed, view=view)

        try:
            result = await view.result
        except asyncio.TimeoutError:
            await view.message.reply('Timed out.')
            return False

        if not result:
            await view.message.reply('Cancelled.')
        return result
