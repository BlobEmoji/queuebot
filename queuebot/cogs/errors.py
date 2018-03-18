# -*- coding: utf-8 -*-
import logging
import traceback
from hashlib import sha256
from os import urandom

from discord import HTTPException
from discord.ext import commands
from discord.ext.commands import Context

from queuebot.cog import Cog
from queuebot.cogs.queue import Suggestion

logger = logging.getLogger(__name__)

IGNORED_ERRORS = (
    commands.CommandNotFound,
    commands.CommandOnCooldown,
    commands.NotOwner
)


def get_trace(error: Exception, limit=15) -> str:
    return ''.join(traceback.format_exception(type(error), error, error.__traceback__, limit=limit))


class Errors(Cog):
    def __init__(self, bot):
        super().__init__(bot)

        # Uhh...I don't know.
        self.__old_on_error = bot.on_error
        bot.on_error = self.on_error

    def __unload(self):
        self.bot.on_error = self.__old_on_error

    async def on_error(self, event_method, *args, **kwargs):
        logger.exception('Error in on_%s:', event_method)

    async def on_command_error(self, ctx: Context, exception):
        # TODO: Handle more errors.
        if isinstance(exception, IGNORED_ERRORS):
            return

        if isinstance(exception, commands.CommandInvokeError):
            # you can use the ray here to get the full trace of a given error with grep via jsk sh
            # for example:
            #  grep -Pzo  '\[84f8c783e9df718d\](.|\n)*\[\/84f8c783e9df718d\]' queuebot.log

            ray = sha256(urandom(32)).hexdigest()[-16:]
            trace = get_trace(exception.original)

            operation_error = isinstance(exception.original, Suggestion.OperationError)

            # Log the error.
            logger.error(f'Bot error [{ray}]: {trace} \n[/{ray}]')

            try:
                await ctx.send(f'Operation error [{ray}]: {exception.original}' if operation_error else
                               f'Sorry, an error has occurred. [{ray}]')
            except HTTPException:
                pass
        elif isinstance(exception, commands.UserInputError):
            await ctx.send('User input error: ' + str(exception))
