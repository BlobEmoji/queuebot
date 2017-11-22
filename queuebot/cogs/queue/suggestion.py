import enum

import discord

import config
from queuebot.cogs.queue import log
from queuebot.utils import SUBMITTER_NOT_FOUND, UPLOADED_EMOJI_NOT_FOUND, SUGGESTION_APPROVED, SUGGESTION_DENIED


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
        if self.is_denied:
            status = 'Denied'
        elif self.is_in_public_queue:
            status = 'In the public approval queue'
        else:
            status = 'In the private council queue'

        return f"""**Suggestion #{self.record['idx']}**

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
