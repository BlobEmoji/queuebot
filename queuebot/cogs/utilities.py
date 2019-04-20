import logging

from discord.ext import commands

from queuebot.checks import is_council
from queuebot.cog import Cog
from queuebot.utils import Table, Timer

logger = logging.getLogger(__name__)


class Utilities(Cog):
    @commands.command()
    @is_council()
    async def ping(self, ctx: commands.Context):
        """Makes the bot respond with \"Pong!\""""
        emoji = '\N{TABLE TENNIS PADDLE AND BALL}'
        with Timer() as timer:
            msg = await ctx.send(f'{emoji} Po\N{EM DASH}')
        await msg.edit(content=f'{emoji} Pong! {timer}')

    @commands.command()
    @is_council()
    async def roles(self, ctx: commands.Context):
        """Views roles in this server."""
        table = Table('ID', 'Name', 'Colour')

        roles = sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True)

        for role in roles:
            table.add_row(str(role.id), role.name, str(role.color))

        rendered = await table.render(ctx.bot.loop)
        await ctx.send('```\n' + rendered + '\n```')


def setup(bot):
    bot.add_cog(Utilities(bot))
