import logging
import traceback

from discord import HTTPException
from discord.ext import commands
from discord.ext.commands import Context

from queuebot.cog import Cog
from queuebot.cogs.queue import Suggestion

logger = logging.getLogger(__name__)

IGNORED_ERRORS = {
    commands.CommandNotFound,
    commands.CommandOnCooldown,
    commands.NotOwner
}


def get_trace(error: Exception) -> str:
    return ''.join(traceback.format_exception(type(error), error, error.__traceback__, limit=15))


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
        if type(exception) in IGNORED_ERRORS:
            return

        if isinstance(exception, commands.CommandInvokeError):
            if isinstance(exception.original, Suggestion.OperationError):
                return await ctx.send(f'Operation error: {exception.original}')

            # Log the error.
            logger.error('Bot error: %s', get_trace(exception.original))

            try:
                await ctx.send("Sorry, an error has occurred.")
            except HTTPException:
                pass
        elif isinstance(exception, commands.UserInputError):
            await ctx.send('User input error: ' + str(exception))
