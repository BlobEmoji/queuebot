from typing import List

import discord

from queuebot.cog import Cog


def format_emoji_list(guild: discord.Guild) -> List[str]:
    """Formats the emoji list for a guild."""

    # The longest output per line we can generate is 97 characters long, if an emoji has a 32 character long name
    # <a:aaaabbbbcccceeeeffffgggghhhhiiii:123456789123456789123> = `:aaaabbbbcccceeeeffffgggghhhhiiii:`

    # A fully boosted server can hold 500 emoji, meaning we may need up to 24.5 (25) messages
    # To allow typing below the emoji list we evenly divide up the emoji over all the messages

    # Group emoji like blobwave and ablobwave next to each other
    emoji = sorted(guild.emojis, key=lambda x: (x.name[1:].lower() if x.animated else x.name.lower(), x.animated))

    messages = []

    total = max(len(guild.emojis), 25)
    per = int(round(total / 25, 0))

    for idx in range(0, total, per):
        messages.append('\n'.join(f'{em} = `:{em.name}:`' for em in emoji[idx:idx + per]) or '\u200b')

    return messages


class EmojiList(Cog):
    @Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, *_):
        if guild.id not in self.config.blob_guilds:
            return

        channel = discord.utils.get(guild.text_channels, name='emoji-list')

        if channel is None:  # Server is not set up properly yet
            return

        formatted = format_emoji_list(guild)
        messages = await channel.history().filter(lambda m: m.author == self.bot.user).flatten()

        if not messages:
            for page in formatted:
                await channel.send(page)
            return

        messages.sort(key=lambda x: x.id)

        for message, content in zip(messages, formatted):
            if message.content == content:
                continue

            await message.edit(content=content)


async def setup(bot):
    await bot.add_cog(EmojiList(bot))
