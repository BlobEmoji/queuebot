# -*- coding: utf-8 -*-
import datetime
import enum
import logging

import discord
from discord.ext import commands

from queuebot.utils import (SUBMITTER_NOT_FOUND, SUGGESTION_APPROVED,
                            SUGGESTION_DENIED, UPLOADED_EMOJI_NOT_FOUND,
                            name_id)

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
        return '<Suggestion idx={0[idx]} user_id={0[user_id]} upvotes={0[upvotes]} downvotes={0[downvotes]}>' \
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

        embed = discord.Embed(title=f'Suggestion #{self.idx} :{self.record["emoji_name"]}:',
                              color=color, description=self.status)
        if self.record['note']:
            embed.description = f'Note: {self.record["note"]}'
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

    async def process_vote(self, vote_emoji: discord.PartialEmoji, vote_type: VoteType, message_id: int, who: int):
        """
        Processes a vote for this suggestion.

        Internally, the upvotes/downvotes column in the database is updated, and a vote check occurs.
        This method is also called for public queue votes, but we do not check those votes, only tally them.

        Parameters
        ----------
        vote_emoji : discord.PartialEmoji
            The emoji that was used to vote. This will determine whether the vote is for or against the suggestion.
        vote_type : VoteType
            The type of vote.
        message_id : int
            The message ID that was voted on.
        who : int
            The ID of the user that voted.
        """
        log.debug(
            'Processing vote! (suggestion: %s) (vote: vote_emoji=%s, operator=%s, message_id=%d, who=%d)',
            self, vote_emoji, vote_type.operator, message_id, who
        )

        # Calculate the column to modify depending on which emoji was reacted with.
        approval = vote_emoji.id == self.bot.config.approve_emoji_id
        vote_target = 'upvotes' if approval else 'downvotes'

        await self.db.execute(
            f"""
            UPDATE suggestions
            SET {vote_target} = {vote_target} {vote_type.operator} 1
            WHERE idx = $1
            """,
            self.idx
        )
        await self.update_inplace()

        if self.record['public_message_id'] is not None:
            # don't keep track of individual votes for suggestions in the public
            # queue.
            return

        column = "has_approved" if approval else "has_denied"
        await self.db.execute(
            f"""
            INSERT INTO council_votes (suggestion_index, user_id, {column}) VALUES
            ($1, $2, $3::BOOLEAN)
            ON CONFLICT (suggestion_index, user_id)
            DO UPDATE SET
            {column} = $3::BOOLEAN
            """,
            self.idx, who, vote_type == vote_type.YAY
        )

        await self.check_council_votes()

    async def delete_from_council_queue(self):
        """Deletes the voting message for this suggestion from the council queue."""
        log.debug('Removing %s from council queue.', self)
        council_queue = self.bot.get_channel(self.bot.config.council_queue)

        # Delete the message in the council queue (cleanup).
        council_message = await council_queue.get_message(self.record['council_message_id'])
        await council_message.delete()

        # Set this suggestion's council queue message ID to null.
        await self.db.execute("""
            UPDATE suggestions
            SET council_message_id = NULL
            WHERE idx = $1
        """, self.idx)
        await self.update_inplace()

    async def move_to_public_queue(self, *, who=None, reason=None):
        """
        Moves this suggestion to the public queue for the masses to vote on.

        This will have several effects:
        - The suggestion will be pushed the approval queue.
        - The database entry will be updated appropriately.
        - The message in the public suggestions channel will be deleted.
        - The message in the private council queue will be deleted.
        - The emoji itself will be deleted, because we don't need it anymore.
          This bot does not handle anything from here on out.

        Parameters
        ----------
        who : discord.User, optional
            The user that forcibly approved this emoji, if any.
        reason : str, optional
            The reason given for the forced approval of this emoji.
        """
        if self.is_in_public_queue:
            raise self.OperationError('This emoji is already in the approval queue.')
        elif self.is_denied:
            raise self.OperationError('This emoji has already been denied.')

        log.info('Moving %s to the public queue.', self)

        user_id = self.record['user_id']
        user = self.bot.get_user(user_id)
        emoji = self.bot.get_emoji(self.record['emoji_id'])

        if not user:
            await self.bot.log(SUBMITTER_NOT_FOUND.format(action='move to approval queue', suggestion=self.record))

        if not emoji:
            await self.bot.log(UPLOADED_EMOJI_NOT_FOUND.format(action='move to approval queue', suggestion=self.record))
            return

        changelog = self.bot.get_channel(self.bot.config.council_changelog)
        queue = self.bot.get_channel(self.bot.config.approval_queue)

        await changelog.send(
            f'<:{self.bot.config.approve_emoji}> moved to {queue.mention}: {emoji} (by <@{user_id}>)'
        )

        async with self.db.acquire() as conn:
            async with conn.transaction():
                # first attempt to push to approval queue..
                msg = await queue.send(emoji)

                # then update the entry, including resetting the votes
                await conn.execute(
                    """
                    UPDATE suggestions
                    SET public_message_id = $1,
                    council_approved = TRUE,
                    forced_reason = $2,
                    forced_by = $3,
                    validation_time = $4,
                    upvotes = 0,
                    downvotes = 0
                    WHERE idx = $5
                    """,
                    msg.id, reason, who, datetime.datetime.utcnow(), self.idx
                )

                # delete from suggestions channel
                # we do this first, because if it fails, it means the emoji will linger in council queue
                # and approval queue will have no method of voting. this prevents damage to this suggestion's data.
                await self.delete_from_suggestions_channel()

                # since that worked, we can now add the reactions
                await msg.add_reaction(self.bot.config.approve_emoji)
                await msg.add_reaction(self.bot.config.deny_emoji)

            # now the record has been safely updated, and the emoji successfully mirrored to approval, we
            # can finally remove it from the queue and delete its emoji.
            await self.delete_from_council_queue()
            await emoji.delete()

        log.info('Set public_message_id -> %d', msg.id)

        await self.update_inplace()

        if user:
            try:
                await user.send(SUGGESTION_APPROVED)
            except discord.HTTPException as exc:
                await self.bot.log(
                    f'\N{WARNING SIGN} Failed to DM `{name_id(user)}` about their approved emoji: `{exc}`'
                )

    async def remove_from_public_queue(self):
        """Removes an entry from the public queue."""

        public_queue = self.bot.get_channel(self.bot.config.approval_queue)
        try:
            msg = await public_queue.get_message(self.record["public_message_id"])
        except discord.NotFound:
            return

        await msg.delete()

    async def deny(self, *, who=None, reason=None, revoke=False):
        """
        Denies this emoji, removing it from the suggestions channel and council
        queue.

        Parameters
        ----------
        who : discord.User, optional
            The user that forcibly denied this emoji, if any.
        reason : str, optional
            The reason given for the forced denial of this emoji.
        revoke : bool, optional
            Indicates whether the emoji was revoked by the submitter.
        """

        # Sane checks for command usage.
        if self.is_in_public_queue:
            raise self.OperationError("This emoji can only be denied while in the council queue.")
        if self.is_denied:
            raise self.OperationError("This emoji has already been denied.")

        user_id = self.record['user_id']
        user = self.bot.get_user(user_id)
        emoji = self.bot.get_emoji(self.record['emoji_id'])

        if not emoji:
            await self.bot.log(UPLOADED_EMOJI_NOT_FOUND.format(action='deny', suggestion=self.record))
            # this is NOT an operation error
            raise RuntimeError("Error denying emoji: the uploaded emoji was not found.")

        if not user:
            await self.bot.log(SUBMITTER_NOT_FOUND.format(action='deny', suggestion=self.record))

        await self.db.execute(
            """
            UPDATE suggestions
            SET council_approved = FALSE,
            forced_reason = $1,
            forced_by = $2,
            validation_time = $3,
            revoked = $4::BOOLEAN
            WHERE idx = $5
            """,
            reason, who, datetime.datetime.utcnow(), revoke, self.idx
        )

        await self.update_inplace()

        changelog = self.bot.get_channel(self.bot.config.council_changelog)

        action = 'revoked' if revoke else 'denied'
        await changelog.send(f'<:{self.bot.config.deny_emoji}> {action}: {emoji} (by <@{user_id}>)')

        await self.delete_from_suggestions_channel()
        await self.delete_from_council_queue()
        await emoji.delete()

        if user and not revoke:
            try:
                await user.send(SUGGESTION_DENIED)
            except discord.HTTPException as exc:
                await self.bot.log(
                    f'\N{WARNING SIGN} Failed to DM `{name_id(user)}` about their denied emoji: `{exc}`'
                )

    async def check_council_votes(self):
        """
        Checks the amount of upvotes and downvotes for this suggestion, and performs a denial or transfer to the public
        queue if applicable.

        The conclusion logic is identical to b1nb0t.
        """
        upvotes = self.record['upvotes']
        downvotes = self.record['downvotes']

        if upvotes + downvotes < self.bot.config.required_votes:
            # Total number of votes doesn't meet the threshold, no point taking any further action.
            return

        if upvotes - downvotes >= self.bot.config.required_difference:
            await self.move_to_public_queue()
        elif downvotes - upvotes >= self.bot.config.required_difference:
            await self.deny()

    async def delete_from_suggestions_channel(self):
        """Deletes the suggestion message from the suggestions channel."""
        message_id = self.record['suggestions_message_id']

        if not message_id:
            log.debug('No suggestions_message_id associated with this suggestion.')
            return

        channel = self.bot.get_channel(self.bot.config.suggestions_channel)

        try:
            message = await channel.get_message(message_id)
            await message.delete()
            log.debug('Removed message %d from suggestions channel.', message.id)
        except discord.HTTPException as exc:
            await self.bot.log(
                f"\N{WARNING SIGN} Failed to delete suggestion #{self.idx}'s message in "
                f"<#{self.bot.config.suggestions_channel}>: `{exc}`"
            )
            log.exception("Failed to delete %s's suggestion message ID:", self)

    async def update_inplace(self):
        """Updates the internal state of this suggestion from the Postgres database."""
        self.record = await self.db.fetchrow(
            'SELECT * FROM suggestions WHERE idx = $1',
            self.idx
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

    @classmethod
    async def convert(cls, _ctx, argument: str):
        if not argument.isdigit():
            raise commands.BadArgument('Invalid suggestion ID: not a numeral.') from None

        try:
            sugg_id = int(argument)
            return await cls.get_from_id(sugg_id)
        except Suggestion.NotFound:
            raise commands.BadArgument('Suggestion not found.') from None
