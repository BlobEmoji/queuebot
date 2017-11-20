# -*- coding: utf-8 -*-
import asyncio
import enum
import io
import logging
import re

import discord
from discord.ext import commands

import config
from queuebot.checks import is_bot_admin
from queuebot.cog import Cog
from queuebot.utils.formatting import name_id
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


class Suggestion:
    """A suggestion in a queue."""

    #: The asyncpg pool.
    db = None

    # the discord bot
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

    def __init__(self, record):
        self.record = record

    def __repr__(self):
        return '<Suggestion idx={0[idx]} user_id={0[user_id]} upvotes={0[upvotes]} downvotes={0[downvotes]}>'\
            .format(self.record)

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

            user_id = self.record['user_id']
            user = self.bot.get_user(user_id)
            emoji = self.bot.get_emoji(self.record['emoji_id'])

            changelog = self.bot.get_channel(config.changelog)
            queue = self.bot.get_channel(config.approval_queue)

            await changelog.send(
                f'<{config.approve_emoji}> moved to {queue.mention}: {emoji} (by <@{user_id}>)'
            )
            await emoji.delete()

            msg = await queue.send(emoji)
            await msg.add_reaction(config.approve_emoji)
            await msg.add_reaction(config.deny_emoji)

            await user.send(SUGGESTION_APPROVED)

        elif downvotes >= 10 and downvotes - upvotes >= 5 and upvotes + downvotes >= 15:
            user_id = self.record['user_id']
            user = self.bot.get_user(user_id)
            emoji = self.bot.get_emoji(self.record['emoji_id'])

            changelog = self.bot.get_channel(config.changelog)

            await changelog.send(f'<{config.deny_emoji}> denied: {emoji}')
            await emoji.delete()

            await user.send(SUGGESTION_DENIED)

    async def update_inplace(self):
        """Updates the internal state of this Suggestion from Postgres."""
        self.record = await self.db.fetchrow(
            'SELECT * FROM suggestions WHERE idx = $1',
            self.record['idx']
        )
        log.debug('Updated suggestion inplace. %s', self)

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
        if message.channel.id != config.suggestions_channel:
            return

        if not message.attachments:
            await message.delete()
            return await message.author.send(BAD_SUGGESTION_MSG)

        attachment = message.attachments[0]

        if not attachment.filename.endswith(('.png', '.jpg')):
            await message.delete()
            return await message.author.send(BAD_SUGGESTION_MSG)

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
        if not is_vote(emoji, channel_id):
            return

        log.debug('Received reaction add.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(message_id)
            await s.process_vote(emoji, Suggestion.VoteType.YAY, message_id)

    async def on_raw_reaction_remove(self, emoji: discord.PartialReactionEmoji, message_id: int,
                                     channel_id: int, user_id: int):
        if not is_vote(emoji, channel_id):
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
