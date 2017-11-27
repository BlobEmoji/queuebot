# -*- coding: utf-8 -*-
import inspect
import logging

from discord.ext import commands

from queuebot.checks import is_bot_admin, is_council
from queuebot.cog import Cog
from queuebot.utils import Timer, Table

logger = logging.getLogger(__name__)


class Utilities(Cog):
    @commands.command()
    @is_council()
    async def help(self, ctx: commands.Context):
        """Shows this help message."""

        # Use a Paginator, so if we go over the 2,000 character limit, we will send multiple messages.
        paginator = commands.Paginator(prefix='', suffix='')

        # Header
        paginator.add_line(f'**{ctx.bot.user.name} Command Reference:**')
        paginator.add_line()

        # `Group`s are `Command`s, so we cannot use `Command` in our `isinstance` checks here.
        regular_commands = [c for c in ctx.bot.commands if not isinstance(c, commands.Group)]
        groups = [c for c in ctx.bot.commands if isinstance(c, commands.Group)]

        def format_cmd(cmd):
            checks = [check.__qualname__ for check in cmd.checks]
            admin = ' Usable by bot admins only.' if any('is_bot_admin' in check for check in checks) else ''
            return f'`{ctx.prefix}{cmd.signature}`: {cmd.help}' + admin

        for cmd in regular_commands:
            paginator.add_line(format_cmd(cmd))

        for group in groups:
            paginator.add_line()

            # The group's help message acts as a category header. Your command group docstrings should be
            # like """Infractions""" or """Queue Management""", as they will be displayed here.
            paginator.add_line(f'**{group.help}**')
            paginator.add_line()

            if len(inspect.signature(group.callback).parameters) > 2:
                # The @group() command has arguments other than self and ctx, it probably does something. Add it here.
                # Keep in mind that command groups are technically commands.
                paginator.add_line(format_cmd(group))

            # Add all subcommands.
            for cmd in group.commands:
                paginator.add_line(format_cmd(cmd))

            paginator.add_line()

        for page in paginator.pages:
            await ctx.send(page)

    @commands.group(aliases=['w'])
    async def wrench(self, ctx: commands.Context):
        """Bot Administration"""

    @wrench.command()
    @is_bot_admin()
    async def reload(self, ctx: commands.Context):
        """Reloads all extensions."""
        try:
            for name in ctx.bot.to_load:
                ctx.bot.unload_extension(name)
                ctx.bot.load_extension(name)
        except Exception:
            await ctx.send("An error has occurred while reloading.")
            logger.exception('Error has occurred while reloading:')
        else:
            await ctx.send('Reloaded.')

    @commands.command()
    @is_council()
    async def ping(self, ctx: commands.Context):
        """Makes the bot respond with \"Pong!\""""
        with Timer() as timer:
            msg = await ctx.send('Po\N{EM DASH}')
        await msg.edit(content=f'Pong! {timer}')

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
