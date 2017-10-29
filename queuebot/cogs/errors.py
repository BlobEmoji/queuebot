import logging
import traceback

from discord import HTTPException
from discord.ext import commands
from discord.ext.commands import Context

from queuebot.cog import Cog

logger = logging.getLogger(__name__)

IGNORED_ERRORS = {
    commands.CommandNotFound,
    commands.CommandOnCooldown,
    commands.NotOwner
}


class Errors(Cog):
    async def on_command_error(self, ctx: Context, exception):
        # TODO: Handle more errors.
        if type(exception) in IGNORED_ERRORS:
            return

        if isinstance(exception, commands.CommandInvokeError):
            # Log the error.
            error = exception.original
            trace = ''.join(traceback.format_exception(type(error), error, error.__traceback__, limit=15))
            logger.fatal('Bot error: %s', trace)

            try:
                await ctx.send("Sorry, a fatal error has occurred.")
            except HTTPException:
                pass
        elif isinstance(exception, commands.UserInputError):
            await ctx.send('User input error: ' + str(exception))
