import asyncio

import discord
from discord.ext import commands


class Context(commands.Context):
    async def confirm(self, description=None, *, embed=None, title=None, color=None):
        decision_emojis = [
            self.bot.get_emoji(self.bot.config.approve_emoji_id),
            self.bot.get_emoji(self.bot.config.deny_emoji_id),
        ]

        embed = embed or discord.Embed()
        embed.color = color or discord.Colour.red()
        embed.title = title or 'Are you sure?'
        embed.set_footer(text=str(self.author), icon_url=self.author.avatar_url)
        embed.description = description

        message = await self.send(embed=embed)
        for emoji in decision_emojis:
            await message.add_reaction(emoji)

        def check(reaction, user):
            return user == self.author and \
                isinstance(reaction.emoji, discord.Emoji) and \
                reaction.emoji in decision_emojis

        try:
            reaction, user = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await self.send('Timed out.')
            return False

        result = reaction.emoji == decision_emojis[0]

        if not result:
            await self.send('Cancelled.')
        return result
