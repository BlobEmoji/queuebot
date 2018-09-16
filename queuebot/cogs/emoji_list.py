from typing import List

import discord

from queuebot.cog import Cog


def format_emoji_list(guild: discord.Guild) -> List[str]:
    """Formats the emoji list for a guild."""

    # the longest output per line we can generate is 97 characters long, if an emoji has a 32 character long name
    # <a:aaaabbbbcccceeeeffffgggghhhhiiii:123456789123456789123> = `:aaaabbbbcccceeeeffffgggghhhhiiii:`

    # a single Discord server can hold 100 emoji total, so we need to send at most 5 messages containing the emoji list
    # if there aren't enough emoji in the server we send a zero width space instead of the page
    # to allow typing under the list and avoid having to send more messages later

    # prepare the five empty messages
    output = ['\u200b', '\u200b', '\u200b', '\u200b', '\u200b']
    emoji = sorted(guild.emojis, key=lambda x: (x.animated, x.name.lower()))

    # split the emoji into chunks of 20 and generate the emoji list pages
    for idx, chunk in enumerate(emoji[x:x + 20] for x in range(0, len(emoji), 20)):
        msg = '\n'.join(f'{emoji} = `:{emoji.name}:`' for emoji in chunk)
        output[idx] = msg

    return output


class EmojiList(Cog):
    async def on_guild_emojis_update(self, guild: discord.Guild, *_):
        if guild.id not in self.config.blob_guilds:
            return

        formatted = format_emoji_list(guild)
        channel = discord.utils.get(guild.text_channels, name='emoji-list')

        if channel is None:
            return  # this server is not set up properly yet

        messages = await channel.history().filter(lambda m: m.author == self.bot.user).flatten()

        if not messages:
            for page in formatted:
                await channel.send(page)
            return

        messages.sort(key=lambda x: x.id)

        for idx, message in enumerate(messages):
            await message.edit(content=formatted[idx])
