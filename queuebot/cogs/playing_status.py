import asyncio
import random

import discord

from queuebot.cog import Cog

STATUSES = [
    (discord.ActivityType.watching, '{user.name}'),
    (discord.ActivityType.watching, '#suggestions'),
    (discord.ActivityType.watching, 'blobs as they come in'),
    (discord.ActivityType.playing, 'with blobs'),
    (discord.ActivityType.listening, 'blob radio')
]


class PlayingStatus(Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.rotate_forever())

    def generate_activity(self):
        """Generate a random :class:`discord.Activity`."""
        random_council_member = self.get_random_council()
        activity_type, format_string = random.choice(STATUSES)

        return discord.Activity(
            type=activity_type,
            name=format_string.format(user=random_council_member)
        )

    def get_random_council(self) -> discord.Member:
        """Return a random council member."""
        council_role_id = list(self.bot.council_roles)[0]
        council_role = discord.utils.get(self.bot.blob_emoji.roles, id=council_role_id)
        return random.choice(council_role.members)

    async def rotate_forever(self):
        await self.bot.wait_until_ready()

        while True:
            await self.rotate()
            await asyncio.sleep(60 * 60)

    async def rotate(self):
        """Change the bot's presence to a random activity."""
        activity = self.generate_activity()
        await self.bot.change_presence(activity=activity)
