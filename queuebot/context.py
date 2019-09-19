import asyncio

import discord
from discord.ext import commands


class Context(commands.Context):
    async def confirm(self, description=None, *, embed=None, title=None, color=None):
        decision_emojis = [
            self.bot.config.approve_emoji_id,
            self.bot.config.deny_emoji_id,
        ]

        embed = embed if embed is not None else discord.Embed()
        embed.color = color or discord.Colour.red()
        embed.title = title or 'Are you sure?'
        embed.set_footer(text=str(self.author), icon_url=self.author.avatar_url)
        embed.description = description

        message = await self.send(embed=embed)
        for emoji_id in decision_emojis:
            await message.add_reaction(self.bot.get_emoji(emoji_id))

        def check(payload):
            return payload.user_id == self.author.id and \
                payload.emoji.is_custom_emoji() and \
                payload.emoji.id in decision_emojis

        try:
            payload = await self.bot.wait_for('raw_reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await self.send('Timed out.')
            return False

        result = payload.emoji.id == decision_emojis[0]

        if not result:
            await self.send('Cancelled.')
        return result
