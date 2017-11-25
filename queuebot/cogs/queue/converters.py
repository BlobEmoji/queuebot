import asyncio

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

class PartialSuggestionConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            sugg_id = int(argument)
            suggestion = await Suggestion.get_from_id(sugg_id)
            return (suggestion.record["idx"], suggestion.emoji_url)
        except (ValueError, Suggestion.NotFound):
            if argument.startswith(("http://", "https://")):
                await asyncio.sleep(1)  # wait up to a second for the embed to load in
                if ctx.message.embeds and ctx.message.embeds[0].image:
                    return (None, ctx.message.embeds[0].image.proxy_url)
            
            raise commands.BadArgument("Couldn't resolve to suggestion or image.")
