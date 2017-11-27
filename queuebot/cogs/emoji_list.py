# -*- coding: utf-8 -*-
from typing import List

import discord

from config import blob_guilds
from queuebot.cog import Cog


def format_emoji_list(guild: discord.Guild) -> List[str]:
    """Formats the emoji list for a guild."""

    output = ['\u200b', '\u200b']
    emoji = sorted(guild.emojis, key=lambda x: x.id)

    # Since messages are 2000 characters at most, only 27 emoji can fit on a page.
    for idx, chunk in enumerate(emoji[x:x + 27] for x in range(0, len(emoji), 27)):
        msg = '\n'.join(f'{emoji} = `:{emoji.name}:`' for emoji in chunk)
        output[idx] = msg

    return output


class EmojiList(Cog):
    async def on_guild_emojis_update(self, guild: discord.Guild, *_):
        if guild.id not in blob_guilds:
            return

        formatted = format_emoji_list(guild)
        channel = discord.utils.get(guild.text_channels, name='emoji-list')

        messages = await channel.history().filter(lambda m: m.author == self.bot.user).flatten()

        if not messages:
            # Guilds can have a maximum of 50 emoji, which makes up 2 messages.
            # One message can only fit 27 entries, so we need two messages here.
            for idx in range(2):
                await channel.send(formatted[idx])
            return

        messages.sort(key=lambda x: x.id)

        for idx, message in enumerate(messages):
            await message.edit(content=formatted[idx])
