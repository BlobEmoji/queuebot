from discord.ext import commands
from discord.ext.commands import Context


def is_bot_admin():
    def predicate(ctx: Context) -> bool:
        return ctx.author.id in ctx.bot.admins
    return commands.check(predicate)


def is_council():
    def predicate(ctx: Context) -> bool:
        if not ctx.guild:
            return False

        return any(role.id in ctx.bot.council_roles for role in ctx.author.roles)
    return commands.check(predicate)
