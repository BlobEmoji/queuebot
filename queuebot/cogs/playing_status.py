import asyncio
import random

import discord
from discord.ext import tasks

from queuebot.cog import Cog

STATUSES = [
    (discord.ActivityType.watching, '#submissions'),
    (discord.ActivityType.watching, 'blobs as they come in'),
    (discord.ActivityType.playing, 'with blobs'),
    (discord.ActivityType.listening, 'blob radio')
]


class PlayingStatus(Cog):
    def __init__(self, bot):
        super().__init__(bot)

        self.activity_changer.start()

    def cog_unload(self):
        self.activity_changer.cancel()

    def generate_activity(self):
        """Generate a random :class:`discord.Activity`."""

        activity_type, format_string = random.choice(STATUSES)
        return discord.Activity(type=activity_type, name=format_string)

    @tasks.loop(hours=1)
    async def activity_changer(self):
        """Change the bot's presence to a random activity."""

        activity = self.generate_activity()
        await self.bot.change_presence(activity=activity)

    @activity_changer.before_loop
    async def before_activity(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(PlayingStatus(bot))
