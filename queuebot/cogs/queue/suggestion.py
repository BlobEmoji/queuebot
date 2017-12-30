# -*- coding: utf-8 -*-
import datetime
import enum
import logging
import typing

import discord

import config

# Can these messages be set in the config? Or at least channels/mentions/whatever
from queuebot.utils import SUBMITTER_NOT_FOUND, UPLOADED_EMOJI_NOT_FOUND, SUGGESTION_APPROVED, SUGGESTION_DENIED, \
    name_id

from config import suggestions_channel, required_votes, required_difference

log = logging.getLogger(__name__)


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

    def __eq__(self, other):
        return self.idx == other.idx

    @property
    def idx(self):
        return self.record["idx"]

    @property
    def is_in_public_queue(self):
        return self.record['council_approved'] is True

    @property
    def is_denied(self):
        return self.record['council_approved'] is False  # do not accept None

    @property
    def is_animated(self):
        return self.record["emoji_animated"] is True

    @property
    def emoji(self):
        return self.bot.get_emoji(self.record['emoji_id'])

    @property
    def emoji_name(self):
        return self.record["emoji_name"]

    @property
    def emoji_url(self):
        return f'https://cdn.discordapp.com/emojis/{self.record["emoji_id"]}.{"gif" if self.is_animated else "png"}'

    @property
    def upvotes(self):
        return self.record["upvotes"]

    @property
    def downvotes(self):
        return self.record["downvotes"]

    @property
    def embed(self):
        if self.is_denied:
            color = discord.Color.red()
        elif self.is_in_public_queue:
            color = discord.Color.green()
        else:
            color = discord.Color.blue()

        embed = discord.Embed(title=f'Suggestion #{self.record["idx"]} :{self.record["emoji_name"]}:',
                              color=color, description=self.status)
        embed.set_thumbnail(url=self.emoji_url)
        embed.add_field(name='Score', value=f'\N{BLACK UP-POINTING TRIANGLE} {self.record["upvotes"]} / '
                                            f'\N{BLACK DOWN-POINTING TRIANGLE} {self.record["downvotes"]}')

        submission_time = f'{self.record["submission_time"]} UTC' or 'Unknown submission time'
        embed.add_field(name='Submitted', value=f'By <@{self.record["user_id"]}>\n{submission_time}')

        if self.record['forced_by']:
            verdict = 'Denial' if self.is_denied else 'Approval' if self.is_in_public_queue else '...'

            embed.add_field(name=f'Forced {verdict}', value=f'<@{self.record["forced_by"]}>\n'
                                                            f'Reason: "{self.record["forced_reason"]}"', inline=False)

        return embed

    @property
    def status(self):
        """Returns a human-friendly representation of where this suggestion is at now."""
        if self.is_denied:
            if self.record["validation_time"]:
                status = f'Denied at {self.record["validation_time"]} UTC'
            else:
                status = "Denied"
        elif self.is_in_public_queue:
            if self.record["validation_time"]:
                status = f'Moved to public approval queue at {self.record["validation_time"]} UTC'
            else:
                status = 'In the public approval queue'
        else:
            status = 'In the private council queue'

        return status


    async def process_vote(self, vote_emoji: discord.PartialReactionEmoji, vote_type: VoteType, message_id: int):
        """
        Processes a vote for this suggestion.

        Internally, the upvotes/downvotes column in the database is updated, and a vote check occurs.
        This method is also called for public queue votes, but we do not check those votes, only tally them.
        """
        log.debug(
            'Processing vote! (suggestion: %s) (vote: vote_emoji=%s, operator=%s, message_id=%d)',
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

    async def move_to_public_queue(self, *, who=None, reason=None):
        """Moves this suggestion to the public queue."""
        if self.is_in_public_queue:
            raise self.OperationError(
                "Cannot move this suggestion to the public approval queue -- it is already in the public approval "
                "queue. "
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

        msg = await queue.send(emoji)
        await msg.add_reaction(config.approve_emoji)
        await msg.add_reaction(config.deny_emoji)

        await emoji.delete()
        await self.delete_from_council_queue()
        await self.delete_from_suggestions_channel()

        # Update this suggestion's row in the database to reflect the move to the public queue.
        log.info('Setting public_message_id -> %d', msg.id)
        await self.db.execute(
            """
            UPDATE suggestions
            SET public_message_id = $1,
            council_approved = TRUE,
            forced_reason = $2,
            forced_by = $3,
            validation_time = $4
            WHERE idx = $5
            """,
            msg.id, reason, who, datetime.datetime.utcnow(), self.record['idx']
        )
        await self.update_inplace()

        if user:
            try:
                await user.send(SUGGESTION_APPROVED)
            except discord.HTTPException:
                await self.bot.log(f'\N{WARNING SIGN} Failed to DM `{name_id(user)}` about their approved emoji.')

    async def remove_from_public_queue(self):
        """Removes an entry from the public queue."""

        public_queue = self.bot.get_channel(config.approval_queue)
        try:
            msg = await public_queue.get_message(self.record["public_message_id"])
        except discord.NotFound:
            return

        await msg.delete()

    async def deny(self, *, who=None, reason=None, revoke=False):
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

        await self.db.execute(
            """
            UPDATE suggestions
            SET council_approved = FALSE,
            forced_reason = $1,
            forced_by = $2,
            validation_time = $3
            WHERE idx = $4
            """,
            reason, who, datetime.datetime.utcnow(), self.record['idx']
        )

        if revoke:
            await self.db.execute(
                """
                UPDATE suggestions
                SET revoked = TRUE
                WHERE idx = $1
                """,
                self.record['idx']
            )

        await self.update_inplace()

        changelog = self.bot.get_channel(config.council_changelog)

        action = 'revoked' if revoke else 'denied'
        await changelog.send(f'<:{config.deny_emoji}> {action}: {emoji} (by <@{user_id}>)')
        await emoji.delete()
        await self.delete_from_council_queue()
        await self.delete_from_suggestions_channel()

        if user and not revoke:
            try:
                await user.send(SUGGESTION_DENIED)
            except discord.HTTPException:
                await self.bot.log(f'\N{WARNING SIGN} Failed to DM `{name_id(user)}` about their denied emoji.')

    async def reset_votes(self):
        await self.db.execute(
            'UPDATE suggestions SET upvotes = 0, downvotes = 0 WHERE idx = $1', self.record['idx']
        )
        await self.update_inplace()

    async def check_council_votes(self):
        """
        Checks the amount of upvotes and downvotes for this suggestion, and performs a denial or transfer to the council
        queue if applicable.

        The conclusion logic is identical to b1nb0t.
        """
        upvotes = self.record['upvotes']
        downvotes = self.record['downvotes']

        if upvotes + downvotes < required_votes:
            # Total number of votes doesn't meet the threshold, no point taking any further action.
            return

        if upvotes - downvotes >= required_difference:
            # Since we don't track internal queue/public queue votes separately, we'll have to reset the upvotes
            # and downvotes columns.
            await self.reset_votes()
            await self.move_to_public_queue()
        elif downvotes - upvotes >= required_difference:
            await self.deny()

    async def delete_from_suggestions_channel(self):
        """Deletes the suggestion message from the suggestions channel."""
        message_id = self.record['suggestions_message_id']

        if not message_id:
            log.debug('No suggestions_message_id associated with this suggestion.')
            return

        channel = self.bot.get_channel(suggestions_channel)

        try:
            message = await channel.get_message(message_id)
            await message.delete()
            log.debug('Removed message %d from suggestions channel.', message.id)
        except discord.HTTPException:
            await self.bot.log(
                f"\N{WARNING SIGN} Failed to delete suggestion #{self.record['idx']}'s message in "
                f"<#{suggestions_channel}>."
            )
            log.exception("Failed to delete %s\'s suggestion message ID:", self)

    async def update_inplace(self):
        """Updates the internal state of this suggestion from the Postgres database."""
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
