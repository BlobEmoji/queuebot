# -*- coding: utf-8 -*-
import asyncio
import enum
import io
import logging
import re

import discord
from discord.ext import commands

import config
from queuebot.checks import is_bot_admin, is_council, is_police
from queuebot.cog import Cog
from queuebot.utils.formatting import name_id, Table
from queuebot.utils.messages import *


# matches the full string or the name of a custom emoji (since replacements for those might be posted)
NAME_RE = re.compile(r'(\w{1,32}):?\d?')

log = logging.getLogger(__name__)


def is_vote(emoji: discord.PartialReactionEmoji, channel_id: int) -> bool:
    """Checks whether an emoji is the approve or deny emoji and a channel is a suggestion processing channel."""
    if emoji.id is None:
        return False  # not a custom emoji

    if emoji.id not in [config.approve_emoji_id, config.deny_emoji_id]:
        return False

    return channel_id in [config.council_queue, config.approval_queue]


class SuggestionConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            sugg_id = int(argument)
            return await Suggestion.get_from_id(sugg_id)
        except ValueError:
            raise commands.BadArgument('Invalid ID.')
        except Suggestion.NotFound:
            raise commands.BadArgument('Suggestion not found.')


class Suggestion:
    """A suggestion in a queue."""

    #: The asyncpg pool.
    db = None

    #: The Discord bot instance.
    bot = None

    class NotFound(Exception):
        """An exception thrown when a suggestion was not found."""

    class VoteType(enum.Enum):
        """Signifies whether a vote will go against or for a suggestion."""
        YAY = enum.auto()
        NAY = enum.auto()

        @property
        def operator(self):
            return '+' if self is self.YAY else '-'

    class OperationError(Exception):
        pass

    def __init__(self, record):
        self.record = record

    def __repr__(self):
        return '<Suggestion idx={0[idx]} user_id={0[user_id]} upvotes={0[upvotes]} downvotes={0[downvotes]}>'\
            .format(self.record)

    @property
    def is_in_public_queue(self):
        return self.record['public_message_id'] is not None

    @property
    def is_denied(self):
        return self.record['public_message_id'] is None and self.record['council_message_id'] is None

    @property
    def status(self):
        status = 'In the public approval queue' if self.is_in_public_queue else 'In the private council queue'
        return f"""Suggestion #{self.record['idx']}

Submitted by <@{self.record['user_id']}>
Upvotes: **{self.record['upvotes']}** / Downvotes: **{self.record['downvotes']}**
Status: {status}"""

    async def process_vote(self, vote_emoji: discord.PartialReactionEmoji, vote_type: VoteType, message_id: int):
        """Processes a vote for this suggestion."""
        log.debug(
            'Processsing vote! (suggestion: %s) (vote: vote_emoji=%s, operator=%s, message_id=%d)',
            self, vote_emoji, vote_type.operator, message_id
        )

        # Calculate the column to modify depending on which emoji was reacted with.
        vote_target = 'upvotes' if vote_emoji.id == config.approve_emoji_id else 'downvotes'

        await self.db.execute(
            f"""
            UPDATE suggestions
            SET {vote_target} = {vote_target} {vote_type.operator} 1
            WHERE idx = $1
            """,
            self.record['idx']
        )
        await self.update_inplace()

        if self.record['public_message_id'] is not None:
            # Don't process public votes. We still keep track of them, though.
            return

        await self.check_council_votes()

    async def delete_from_council_queue(self):
        """Deletes the voting message for this suggestion from the council queue."""
        log.debug('Removing %s from council queue.', self)
        council_queue = self.bot.get_channel(config.council_queue)

        # Delete the message in the council queue (cleanup).
        council_message = await council_queue.get_message(self.record['council_message_id'])
        await council_message.delete()

        # Set this suggestion's council queue message ID to null.
        await self.db.execute("""
            UPDATE suggestions
            SET council_message_id = NULL
            WHERE idx = $1
        """, self.record['idx'])
        await self.update_inplace()

    async def move_to_public_queue(self):
        """Moves this suggestion to the public queue."""
        if self.is_in_public_queue:
            raise self.OperationError(
                "Cannot move this suggestion to the public queue -- it is already in the public queue."
            )

        log.info('Moving %s to the public queue.', self)

        user_id = self.record['user_id']
        user = self.bot.get_user(user_id)
        emoji = self.bot.get_emoji(self.record['emoji_id'])

        if not user:
            await self.bot.log(SUBMITTER_NOT_FOUND.format(action='move to PQ', suggestion=self.record))

        if not emoji:
            await self.bot.log(UPLOADED_EMOJI_NOT_FOUND.format(action='move to PQ', suggestion=self.record))
            return

        changelog = self.bot.get_channel(config.council_changelog)
        queue = self.bot.get_channel(config.approval_queue)

        await changelog.send(
            f'<:{config.approve_emoji}> moved to {queue.mention}: {emoji} (by <@{user_id}>)'
        )

        # Send it to the public queue, and add the ticks.
        msg = await queue.send(emoji)
        await msg.add_reaction(config.approve_emoji)
        await msg.add_reaction(config.deny_emoji)

        # Delete the emoji, and remove the voting message from the council queue.
        await emoji.delete()
        await self.delete_from_council_queue()

        # Set the public message id.
        log.info('Setting public_messsage_id -> %d', msg.id)
        await self.db.execute(
            """
            UPDATE suggestions
            SET public_message_id = $1
            WHERE idx = $2
            """,
            msg.id, self.record['idx']
        )
        await self.update_inplace()

        if user:
            await user.send(SUGGESTION_APPROVED)

    async def deny(self):
        """Denies this emoji."""
        # Sane checks for command usage.
        if self.is_in_public_queue:
            raise self.OperationError("Can't deny this suggestion -- it's already in the public queue.")
        if self.is_denied:
            raise self.OperationError("Can't deny this suggestion -- it has already been denied.")

        user_id = self.record['user_id']
        user = self.bot.get_user(user_id)
        emoji = self.bot.get_emoji(self.record['emoji_id'])

        if not emoji:
            await self.bot.log(UPLOADED_EMOJI_NOT_FOUND.format(action='deny', suggestion=self.record))
            raise self.OperationError("Error denying -- the uploaded emoji wasn't found.")

        if not user:
            await self.bot.log(SUBMITTER_NOT_FOUND.format(action='deny', suggestion=self.record))

        changelog = self.bot.get_channel(config.council_changelog)

        await changelog.send(f'<:{config.deny_emoji}> denied: {emoji} (by <@{user_id}>)')
        await emoji.delete()
        await self.delete_from_council_queue()

        if user:
            await user.send(SUGGESTION_DENIED)

    async def check_council_votes(self):
        upvotes = self.record['upvotes']
        downvotes = self.record['downvotes']

        # This logic is copied from b1nb0t.
        if upvotes >= 10 and upvotes - downvotes >= 5 and upvotes + downvotes >= 15:
            # Since we don't track internal queue/public queue votes separately, we'll have to reset the upvotes
            # and downvotes columns.
            await self.db.execute(
                'UPDATE suggestions SET upvotes = 0, downvotes = 0 WHERE idx = $1', self.record['idx']
            )
            await self.update_inplace()
            await self.move_to_public_queue()
        elif downvotes >= 10 and downvotes - upvotes >= 5 and upvotes + downvotes >= 15:
            await self.deny()

    async def update_inplace(self):
        """Updates the internal state of this Suggestion from Postgres."""
        self.record = await self.db.fetchrow(
            'SELECT * FROM suggestions WHERE idx = $1',
            self.record['idx']
        )
        log.debug('Updated suggestion inplace. %s', self)

    @classmethod
    async def get_from_id(cls, suggestion_id: int) -> 'Suggestion':
        """Returns a Suggestion instance by ID."""

        record = await cls.db.fetchrow(
            """
            SELECT * FROM suggestions
            WHERE idx = $1
            """,
            suggestion_id
        )

        if not record:
            raise cls.NotFound('Suggestion not found.')

        return cls(record)

    @classmethod
    async def get_from_message(cls, message_id: int) -> 'Suggestion':
        """
        Returns a Suggestion instance by message ID.

        This works for messages in the council queue, or public queue.
        """

        record = await cls.db.fetchrow(
            """
            SELECT * FROM suggestions
            WHERE council_message_id = $1 OR public_message_id = $1
            """,
            message_id
        )

        if not record:
            raise cls.NotFound('Suggestion not found.')

        return cls(record)


class BlobQueue(Cog):
    """Processing blob suggestions on the Blob Emoji server."""

    def __init__(self, bot):
        super().__init__(bot)

        Suggestion.db = bot.db
        Suggestion.bot = bot
        self.voting_lock = asyncio.Lock()

    async def on_message(self, message: discord.Message):
        global log  # Can't access the logger from here for some reason.
        if message.channel.id != config.suggestions_channel:
            return

        if not message.attachments:
            await message.delete()
            return await message.author.send(BAD_SUGGESTION_MSG)

        attachment = message.attachments[0]

        if not attachment.filename.endswith(('.png', '.jpg')):
            await message.delete()
            return await message.author.send(BAD_SUGGESTION_MSG)

        log.info('Saving attachment from %d...', message.id)
        buffer = io.BytesIO()
        await attachment.save(buffer)
        log.info('Saved.')
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

        # log all suggestions to a special channel to keep original files and have history for moderation purposes
        buffer.seek(0)
        log = self.bot.get_channel(config.suggestions_log)
        await log.send(
            f'{name} by {name_id(message.author)} filename: {attachment.filename}'.replace('@', '@\u200b'),
            file=discord.File(buffer, filename=attachment.filename)
        )

        queue = self.bot.get_channel(config.council_queue)
        msg = await queue.send(emoji)

        await msg.add_reaction(config.approve_emoji)
        await msg.add_reaction(config.deny_emoji)

        await self.db.execute(
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
            """,
            message.author.id,
            msg.id,
            emoji.id,
            name
        )

        await message.delete()
        await message.author.send(SUGGESTION_RECIEVED)

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
    async def move_to_public_queue(self, ctx, suggestion: SuggestionConverter):
        """Moves a suggestion to the public queue."""
        log.info('Cmd: moving %s to public queue', suggestion)
        await suggestion.move_to_public_queue()
        await ctx.send(f"Successfully moved #{suggestion.record['idx']}.")

    @commands.command()
    @is_police()
    async def deny(self, ctx, suggestion: SuggestionConverter):
        """Denies an emoji that is currently in the council queue."""
        log.info('Cmd: denying %s', suggestion)
        await suggestion.deny()
        await ctx.send(f"Successfully denied #{suggestion.record['idx']}.")

    @commands.command(aliases=['sg'])
    @is_council()
    async def suggestions(self, ctx):
        """Views recent suggestions."""
        suggestions = [Suggestion(record) for record in await self.db.fetch("""
            SELECT * FROM suggestions
            ORDER BY idx DESC
            LIMIT 10
        """)]

        table = Table('#', 'Name', 'Submitted By', 'Points', 'Status')
        for s in suggestions:
            user = ctx.bot.get_user(s.record['user_id'])
            submitted_by = f'{user} {user.id}' if user else str(s.record['user_id'])

            if s.is_denied:
                status = 'Denied'
            elif s.is_in_public_queue:
                status = 'PQ'
            else:
                status = 'CQ'

            table.add_row(
                str(s.record['idx']), ':' + s.record['emoji_name'] + ':', submitted_by,
                f'▲ {s.record["upvotes"]} / ▼ {s.record["downvotes"]}',
                status
            )

        await ctx.send(
            '```\n' + await table.render(ctx.bot.loop) + '\n```'
        )
