from discord.ext.commands import Context, command

from queuebot.utils import Timer
from ..bot import Queuebot


class Utilities:
    def __init__(self, bot: Queuebot):
        self.bot = bot

    @command()
    async def ping(self, ctx: Context):
        with Timer() as timer:
            msg = await ctx.send('Po\N{EM DASH}')
        await msg.edit(content=f'Pong! {timer}')


def setup(bot: Queuebot):
    bot.add_cog(Utilities(bot))
