from discord.ext import commands
from discord.ext.commands import Context


def is_bot_admin():
    def predicate(ctx: Context) -> bool:
        return ctx.author.id in ctx.bot.admins
    return commands.check(predicate)
