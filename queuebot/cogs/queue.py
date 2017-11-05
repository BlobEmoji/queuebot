# -*- coding: utf-8 -*-
import asyncio
import enum
import io
import logging
import re

from discord import File, Guild, HTTPException, Message, PartialReactionEmoji, utils
from discord.ext.commands import Context, command, group

import config
from queuebot.checks import is_bot_admin
from queuebot.cog import Cog
from queuebot.utils.formatting import name_id


# matches the full string or the name of a custom emoji (since replacements for those might be posted)
NAME_RE = re.compile(r'(\w{1,32}):?\d?')

log = logging.getLogger(__name__)


def is_vote(emoji: PartialReactionEmoji, channel_id: int) -> bool:
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
        return '<Suggestion idx={0[idx]} user_id={0[user_id]} upvotes={0[upvotes]} downvotes={0[downvotes]}>'.format(self.record)

    async def process_vote(self, vote_emoji: PartialReactionEmoji, vote_type: VoteType, message_id: int):
        """Processes a vote for this suggestion."""

        log.debug(
            'Processsing vote! (suggestion: %s) (vote: vote_emoji=%s, operator=%s, message_id=%d)',
            self, vote_emoji, vote_type.operator, message_id
        )

        # Calculate the column to modify depending on which emoji was reacted with.
        vote_target = 'upvotes' if vote_emoji == config.approve_emoji_id else 'downvotes'

        await self.db.execute(
            f"""
            update suggestions
            set {vote_target} = {vote_target} {vote_type.operator} 1
            where idx = $1
            """,
            self.record['idx']
        )
        await self.update_inplace()

    async def update_inplace(self):
        """Updates the internal state of this Suggestion from Postgres."""
        self.record = await self.db.fetchrow(
            'select * from suggestions where idx = $1',
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
            f"""
            select * from suggestions
            where council_message_id = $1 or public_message_id = $1
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
        self.voting_lock = asyncio.Lock()

    async def on_message(self, message: Message):
        if message.channel.id != config.suggestions_channel:
            return

        if not message.attachments:
            await message.delete()
            return await message.author.send(
                'Your suggestion didn\'nt have any files attached, please repost the message and attach the suggestion!'
            )

        attachment = message.attachments[0]

        if not attachment.filename.endswith(('.png', '.jpg')):
            await message.delete()
            return await message.author.send(
                'Your suggestion image must be in png or jpg format, please resubmit it after changing the format!'
            )

        buffer = io.BytesIO()
        await attachment.save(buffer)
        buffer.seek(0)

        try:
            guild = await self.get_buffer_guild()
        except HTTPException:
            await message.delete()

            log = self.bot.get_channel(config.bot_log)
            await log.send('Couldn\'t process suggestion due to having no free emoji or guild slots!')

            return await message.author.send(
                'Your suggestion couldn\'nt be processed! The bot owner has been notified, please try again later.'
            )

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
            file=File(buffer, filename=attachment.filename)
        )

        queue = self.bot.get_channel(config.council_queue)
        msg = await queue.send(emoji)

        await msg.add_reaction(config.approve_emoji)
        await msg.add_reaction(config.deny_emoji)

        await self.db.execute(
            """
            insert into suggestions (
                user_id,
                council_message_id,
                emoji_id,
                emoji_name
            )
            values (
                $1, $2, $3, $4
            )
            """,
            message.author.id,
            msg.id,
            emoji.id,
            name
        )

        await message.delete()
        await message.author.send(
            'Your suggestion has been accepted and will now be voted on by the Blob Council!'
            'You\'ll receive another direct message with updates once it has been voted on!'
        )

    # todo: move blobs from council queue -> public queue, delete from buffer guild
    # note: on move votes have the be reset (or change the schema - don't really mind)
    async def on_raw_reaction_add(self, emoji: PartialReactionEmoji, message_id: int, channel_id: int, user_id: int):
        if not is_vote(emoji, channel_id) or user_id == self.bot.user.id:
            return

        log.debug('Received reaction.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(message_id)
            await s.process_vote(emoji, Suggestion.VoteType.YAY, message_id)

    async def on_raw_reaction_remove(self, emoji: PartialReactionEmoji, message_id: int, channel_id: int, user_id: int):
        if not is_vote(emoji, channel_id) or user_id == self.bot.user.id:
            return

        log.debug('Received reaction.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(message_id)
            await s.process_vote(emoji, Suggestion.VoteType.NAY, message_id)

    async def get_buffer_guild(self) -> Guild:
        """
        Get a guild the bot can upload a temporary emoji to.

        This returns a guild the bot has the manage_emojis permissions in and has fewer than 50 custom emojis.
        If no suitable guild is found a new one is created.

        Raises
        ------
        HTTPException
            The bot is in more than 10 guilds total while creating a new guild.
        """
        def has_emoji_slots(guild: Guild) -> bool:
            return guild.me.guild_permissions.manage_emojis and len(guild.emojis) < 50

        guild = utils.find(has_emoji_slots, self.bot.guilds)
        if guild is not None:
            return guild

        return await self.bot.create_guild('BlobQueue Emoji Buffer')

    @command()
    @is_bot_admin()
    async def buffer_info(self, ctx):
        """Shows information about buffer guilds."""
        try:
            guild = await self.get_buffer_guild()
        except HTTPException:
            await ctx.send('**Error!** No available buffer guild.')

        await ctx.send(f'Current buffer guild: {guild.name} ({len(guild.emojis)}/50 full)')
