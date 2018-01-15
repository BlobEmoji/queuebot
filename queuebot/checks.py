# -*- coding: utf-8 -*-
from discord.ext import commands


def is_bot_admin():
    def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id in ctx.bot.admins
    return commands.check(predicate)


def is_police():
    def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        return any(role.id in ctx.bot.config.authority_roles for role in ctx.author.roles)
    return commands.check(predicate)


def is_council():
    def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        return any(role.id in ctx.bot.council_roles for role in ctx.author.roles)
    return commands.check(predicate)
