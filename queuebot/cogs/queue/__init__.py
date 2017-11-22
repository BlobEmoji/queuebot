# -*- coding: utf-8 -*-
import asyncio
import io
import logging
import re

import discord
from discord.ext import commands

import config
from queuebot.checks import is_bot_admin, is_council, is_police
from queuebot.cog import Cog
from queuebot.cogs.queue.converters import SuggestionConverter
from queuebot.cogs.queue.suggestion import Suggestion
from queuebot.utils.formatting import name_id, Table
from queuebot.utils.messages import *

# Matches the full string or the name of a custom emoji (since replacements for those might be posted).
NAME_RE = re.compile(r'(\w{1,32}):?\d?')

log = logging.getLogger(__name__)


def is_vote(emoji: discord.PartialReactionEmoji, channel_id: int) -> bool:
    """Checks whether an emoji is the approve or deny emoji and a channel is a suggestion processing channel."""
    if emoji.id is None:
        return False  # not a custom emoji

    if emoji.id not in [config.approve_emoji_id, config.deny_emoji_id]:
        return False

    return channel_id in [config.council_queue, config.approval_queue]


class BlobQueue(Cog):
    """Processing blob suggestions on the Blob Emoji server."""

    def __init__(self, bot):
        super().__init__(bot)

        Suggestion.db = bot.db
        Suggestion.bot = bot
        self.voting_lock = asyncio.Lock()

    async def on_message(self, message: discord.Message):
        if message.channel.id != config.suggestions_channel or message.author == self.bot.user:
            return

        async def respond(response):
            try:
                return await message.author.send(response)
            except discord.HTTPException:
                return await message.channel.send(f'{message.author.mention}: {response}', delete_after=25.0)

        if not message.attachments:
            await message.delete()
            await respond(BAD_SUGGESTION_MSG)
            return

        attachment = message.attachments[0]

        if not attachment.filename.endswith(('.png', '.jpg')):
            await message.delete()
            await respond(BAD_SUGGESTION_MSG)
            return

        # Save the emoji image data to an in-memory buffer to upload later, in the logging channel.
        buffer = io.BytesIO()
        await attachment.save(buffer)
        buffer.seek(0)

        try:
            guild = await self.get_buffer_guild()
        except discord.HTTPException:
            await message.delete()

            log = self.bot.get_channel(config.bot_log)
            await log.send('Couldn\'t process suggestion due to having no free emoji or guild slots!')

            return await message.author.send(BOT_BROKEN_MSG)

        # use the messages content or the filename, removing the .png or .jpg extension
        match = NAME_RE.search(message.content)
        if match is not None:
            name = match.groups()[0]
        else:
            # use the first 36 chars of filename, removing the .png or .jpg extension (to make the name max 32 chars)
            name = attachment.filename[:36][:-4]

        emoji = await guild.create_custom_emoji(
            name=name, image=buffer.read(), reason='new blob suggestion'
        )

        queue = self.bot.get_channel(config.council_queue)
        msg = await queue.send(emoji)
        await msg.add_reaction(config.approve_emoji)
        await msg.add_reaction(config.deny_emoji)

        record = await self.db.fetchrow(
            """
            INSERT INTO suggestions (
                user_id,
                council_message_id,
                emoji_id,
                emoji_name
            )
            VALUES (
                $1, $2, $3, $4
            )
            RETURNING idx
            """,
            message.author.id,
            msg.id,
            emoji.id,
            name
        )

        # Log all suggestions to a special channel to keep original files and have history for moderation purposes.
        buffer.seek(0)
        log = self.bot.get_channel(config.suggestions_log)
        await log.send(
            (f'**Submission #{record["idx"]}**\n\n:{name}: by `{name_id(message.author)}`\n'
             f'Filename: {attachment.filename}').replace('@', '@\u200b'),
            file=discord.File(buffer, filename=attachment.filename)
        )

        await message.delete()
        await respond(SUGGESTION_RECIEVED)

    async def on_raw_reaction_add(self, emoji: discord.PartialReactionEmoji, message_id: int,
                                  channel_id: int, user_id: int):
        if user_id == self.bot.user.id or not is_vote(emoji, channel_id):
            return

        log.debug('Received reaction add.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(message_id)
            await s.process_vote(emoji, Suggestion.VoteType.YAY, message_id)

    async def on_raw_reaction_remove(self, emoji: discord.PartialReactionEmoji, message_id: int,
                                     channel_id: int, user_id: int):
        if user_id == self.bot.user.id or not is_vote(emoji, channel_id):
            return

        log.debug('Received reaction remove.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(message_id)
            await s.process_vote(emoji, Suggestion.VoteType.NAY, message_id)

    async def get_buffer_guild(self) -> discord.Guild:
        """
        Get a guild the bot can upload a temporary emoji to.

        This returns a guild the bot has the manage_emojis permissions in and has fewer than 50 custom emojis.
        If no suitable guild is found a new one is created.

        Raises
        ------
        HTTPException
            The bot is in more than 10 guilds total while creating a new guild.
        """
        def has_emoji_slots(guild: discord.Guild) -> bool:
            return guild.owner_id == self.bot.user.id and len(guild.emojis) < 50

        guild = discord.utils.find(has_emoji_slots, self.bot.guilds)
        if guild is not None:
            return guild

        return await self.bot.create_guild('BlobQueue Emoji Buffer')

    @commands.command()
    @is_bot_admin()
    async def buffer_info(self, ctx):
        """Shows information about buffer guilds."""
        try:
            guild = await self.get_buffer_guild()
        except discord.HTTPException:
            await ctx.send('**Error!** No available buffer guild.')

        await ctx.send(f'Current buffer guild: {guild.name} ({len(guild.emojis)}/50 full)')

    @commands.command()
    @is_police()
    async def approve(self, ctx, suggestion: SuggestionConverter):
        """Moves a suggestion from the council queue to the public queue."""
        log.info('%s: moving %s to public queue', ctx.author, suggestion)
        await suggestion.move_to_public_queue()
        await ctx.send(f"Successfully moved #{suggestion.record['idx']}.")

    @commands.command()
    @is_police()
    async def deny(self, ctx, suggestion: SuggestionConverter):
        """Denies an emoji that is currently in the council queue."""
        log.info('%s: denying %s', ctx.author, suggestion)
        await suggestion.deny()
        await ctx.send(f"Successfully denied #{suggestion.record['idx']}.")

    @commands.command()
    @is_council()
    async def status(self, ctx, suggestion: SuggestionConverter):
        """Views the status of a submission."""
        return await ctx.send(suggestion.status)

    @commands.command(aliases=['sg'])
    @is_council()
    async def suggestions(self, ctx, limit: int=10):
        """Views recent suggestions."""
        suggestions = [Suggestion(record) for record in await self.db.fetch("""
            SELECT * FROM suggestions
            ORDER BY idx DESC
            LIMIT $1
        """, limit)]

        table = Table('#', 'Name', 'Submitted By', 'Points', 'Status')
        for s in suggestions:
            user = ctx.bot.get_user(s.record['user_id'])
            submitted_by = f'{user} {user.id}' if user else str(s.record['user_id'])

            if s.is_denied:
                status = 'Denied'
            elif s.is_in_public_queue:
                status = 'AQ'  # The "public queue" is actually called the "approval queue".
            else:
                status = 'CQ'

            table.add_row(
                str(s.record['idx']), ':' + s.record['emoji_name'] + ':', submitted_by,
                f'▲ {s.record["upvotes"]} / ▼ {s.record["downvotes"]}',
                status
            )

        text = '```\n' + await table.render(ctx.bot.loop) + '\n```'

        if len(text) > 2000:
            await ctx.send("Result table was too big. Try lowering the limit.")
        else:
            await ctx.send(text)
