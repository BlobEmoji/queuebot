from discord.ext import commands

from queuebot.cogs.queue.suggestion import Suggestion


class SuggestionConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            sugg_id = int(argument)
            return await Suggestion.get_from_id(sugg_id)
        except ValueError:
            raise commands.BadArgument('Invalid ID.')
        except Suggestion.NotFound:
            raise commands.BadArgument('Suggestion not found.')
