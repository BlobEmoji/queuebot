import asyncio
import functools
import hashlib
import io
import logging
import re
from io import BytesIO
from os import path

import aiohttp
import discord
from PIL import Image
from discord import raw_models
from discord.ext import commands

from queuebot.checks import is_council, is_council_or_cooldown
from queuebot.cog import Cog
from queuebot.cogs.queue.converters import PartialSuggestionConverter, PublicQueueOrEmojiConverter
from queuebot.cogs.queue.suggestion import Suggestion
from queuebot.utils.formatting import name_id, Table
from queuebot.utils.messages import *  # noqa: ignore=F401

# Matches the full string or the name of a custom emoji (since replacements for those might be posted).
NAME_RE = re.compile(r'(\w{2,32}):?\d?')
NOTE_RE = re.compile(r'- ([^-]+)$')

# Matches all characters that can't be an emoji name
SAFETY_RE = re.compile(r'[^a-zA-Z0-9_]')
clean_emoji_name = functools.partial(SAFETY_RE.sub, "_")

# Different vs patterns; Compact = Original, Verbose = Issue #32
COMPACT_VS_JOINER = " \N{SQUARED VS} "
VERBOSE_VS_JOINER = "\n\N{EM SPACE}\N{SQUARED VS}\n"

logger = logging.getLogger(__name__)


class BlobQueue(Cog):
    """Processing blob suggestions on the Blob Emoji server."""

    def __init__(self, bot):
        super().__init__(bot)

        Suggestion.db = bot.db
        Suggestion.bot = bot

        self.voting_lock = asyncio.Lock()
        self.vs_lock = asyncio.Lock()

    def is_vote(self, emoji: discord.PartialEmoji, channel_id: int) -> bool:
        """Checks whether an emoji is the approve or deny emoji and a channel is a suggestion processing channel."""
        if emoji.id is None:
            return False  # not a custom emoji

        if emoji.id not in [self.config.approve_emoji_id, self.config.deny_emoji_id]:
            return False

        return channel_id in [self.config.council_queue, self.config.approval_queue]

    async def on_message(self, message: discord.Message):
        """Handles messages sent in the suggestions channel."""
        if message.channel.id != self.config.suggestions_channel or message.author == self.bot.user:
            return

        async def respond(response: str) -> discord.Message:
            try:
                return await message.author.send(response)
            except discord.HTTPException:
                return await message.channel.send(f'{message.author.mention}: {response}', delete_after=25.0)

        if not message.attachments:
            await message.delete()
            logger.info(f"A suggestion by {message.author.id} was rejected because it had no attachments.")
            await respond(BAD_SUGGESTION_MSG)
            return

        attachment = message.attachments[0]

        if not attachment.filename.endswith(('.png', '.jpg', '.gif')):
            await message.delete()
            logger.info(f"A suggestion by {message.author.id} was rejected because it was in an unsupported format.")
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

            log = self.bot.get_channel(self.config.bot_log)
            logger.info(f"A suggestion by {message.author.id} was not processed due to lack of emoji or guild slots.")
            await log.send("\N{WARNING SIGN} Couldn't process a suggestion due to having no free emoji or guild slots.")

            await message.author.send(BOT_BROKEN_MSG)
            return

        # use the messages content or the filename, removing the .png or .jpg extension
        match = NAME_RE.search(message.content)
        if match is not None:
            name = match.groups()[0]
        else:
            # use the first 36 chars of filename, removing the .png or .jpg extension (to make the name max 32 chars)
            name = attachment.filename[:36][:-4]

        # detect note
        note_match = NOTE_RE.search(message.content)

        if note_match is not None:
            note = note_match.groups()[0][:140]
        else:
            note = None

        logger.debug('Message content: "%s", detected name: "%s", detected note: "%s"', message.content, name, note)

        buffer_content = buffer.read()

        if len(buffer_content) > 261888:
            await message.delete()
            logger.info(f"A suggestion by {message.author.id} was rejected because it was too large.")
            await respond(SUGGESTION_TOO_LARGE)
            return

        emoji = await guild.create_custom_emoji(
            name=clean_emoji_name(name), image=buffer_content, reason='new blob suggestion'
        )

        logger.info(f"Created new emoji by name {name} in guild {guild.id}.")

        buffer.seek(0)  # seek back again for test image impl

        try:
            emoji_im = Image.open(buffer)
        except OSError:
            queue_file = None  # fallback
        else:
            queue_file = await self.bot.loop.run_in_executor(None, self.test_backend, emoji_im)

        animated = queue_file.filename.endswith(".gif")

        queue = self.bot.get_channel(self.config.council_queue)
        msg = await queue.send(emoji, file=queue_file)
        await msg.add_reaction(self.config.approve_emoji)
        await msg.add_reaction(self.config.deny_emoji)

        record = await self.db.fetchrow(
            """
            INSERT INTO suggestions (
                user_id,
                council_message_id,
                emoji_id,
                emoji_name,
                submission_time,
                suggestions_message_id,
                emoji_animated,
                note
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            RETURNING idx
            """,
            message.author.id,
            msg.id,
            emoji.id,
            name,
            message.created_at,
            message.id,
            animated,
            note
        )

        # Log all suggestions to a special channel to keep original files and have history for moderation purposes.
        buffer.seek(0)
        file_hash = hashlib.sha256(buffer.read()).hexdigest()
        buffer.seek(0)
        log = self.bot.get_channel(self.config.suggestions_log)
        await log.send(
            (f'**Submission #{record["idx"]}**\n\n:{name}: by `{name_id(message.author)}`\n'
             f'Filename: {attachment.filename}\nHash: `{file_hash}`').replace('@', '@\u200b'),
            file=discord.File(buffer, filename=attachment.filename)
        )

        await message.add_reaction('\N{EYES}')
        await respond(SUGGESTION_RECEIVED.format(suggestion=emoji))

    async def on_raw_reaction_add(self, payload: raw_models.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id or not self.is_vote(payload.emoji, payload.channel_id):
            return

        logger.debug('Received reaction add.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(payload.message_id)
            await s.process_vote(payload.emoji, Suggestion.VoteType.YAY, payload.message_id, payload.user_id)

    async def on_raw_reaction_remove(self, payload: raw_models.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id or not self.is_vote(payload.emoji, payload.channel_id):
            return

        logger.debug('Received reaction remove.')

        async with self.voting_lock:
            s = await Suggestion.get_from_message(payload.message_id)
            await s.process_vote(payload.emoji, Suggestion.VoteType.NAY, payload.message_id, payload.user_id)

    def has_emoji_slots(self, guild: discord.Guild) -> bool:
        return guild.owner_id == self.bot.user.id and len(guild.emojis) < 50

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

        guild = discord.utils.find(self.has_emoji_slots, self.bot.guilds)
        if guild is not None:
            return guild

        logger.info("Creating new buffer emoji guild..")
        return await self.bot.create_guild('BlobQueue Emoji Buffer')

    @commands.command()
    @commands.is_owner()
    async def buffer_info(self, ctx):
        """Shows information about buffer guilds."""
        try:
            guild = await self.get_buffer_guild()
        except discord.HTTPException:
            await ctx.send('**Error!** No available buffer guild.')

        await ctx.send(f'Current buffer guild: {guild.name} ({len(guild.emojis)}/50 full)')

    @commands.command()
    @is_council()
    async def approve(self, ctx, suggestion: Suggestion, *, reason=None):
        """Moves a suggestion from the council queue to the public queue."""
        embed = discord.Embed()
        embed.set_image(url=suggestion.emoji_url)
        if not await ctx.confirm('Are you sure that you want to **approve** this suggestion?', embed=embed,
                                 color=discord.Color.green()):
            return

        logger.info('%s: Moving %s to public (approval) queue.', ctx.author, suggestion)
        reason = reason or None  # do not push empty strings
        await suggestion.move_to_public_queue(who=ctx.author.id, reason=reason)
        await self.bot.log(f"<:{self.config.approve_emoji}> Suggestion #{suggestion.idx} force approved by "
                           f"{ctx.author.mention} ({ctx.author.id})\n"
                           f"{'Reason: ' + reason if reason else 'No reason provided.'}")
        await ctx.send(f"Successfully moved #{suggestion.idx}.")

    @commands.command()
    @is_council()
    async def deny(self, ctx, suggestion: Suggestion, *, reason=None):
        """Denies an emoji that is currently in the council queue."""
        embed = discord.Embed()
        embed.set_image(url=suggestion.emoji_url)
        if not await ctx.confirm('Are you sure you want to **deny** this suggestion?', embed=embed):
            return

        logger.info('%s: Denying %s.', ctx.author, suggestion)
        reason = reason or None  # do not push empty strings
        await suggestion.deny(who=ctx.author.id, reason=reason)
        await self.bot.log(f"<:{self.config.deny_emoji}> Suggestion #{suggestion.idx} force denied by "
                           f"{ctx.author.mention} ({ctx.author.id})\n"
                           f"{'Reason: ' + reason if reason else 'No reason provided.'}")
        await ctx.send(f"Successfully denied #{suggestion.idx}.")

    @commands.command()
    @is_council()
    async def vs(self, ctx, *emoji: PublicQueueOrEmojiConverter):
        """Creates VS vote between two emoji in the public queue."""
        if self.vs_lock.locked():
            await ctx.send("A VS command is already being run, or has been run too recently.")
            return

        async with self.vs_lock:

            if len(emoji) < 2:
                await ctx.send("Need at least 2 emoji to do VS vote.")
                return

            if len(emoji) > 6:
                await ctx.send("Refusing to do VS vote of greater than 6 emoji.")
                return

            id_set = set(x[1] for x in emoji)
            if len(id_set) < len(emoji):
                await ctx.send("Can't have a VS vote with the same emoji appearing more than once.")
                return

            async with ctx.typing():

                temp_emotes = []
                for index, this_emoji in enumerate(emoji):
                    buffer_guild = await self.get_buffer_guild()
                    emoji_name = clean_emoji_name(f"{this_emoji[3][0:30]}_{index+1}")

                    async with self.bot.session.get(this_emoji[2]) as resp:
                        temp_emotes.append(await buffer_guild.create_custom_emoji(
                            name=emoji_name, image=await resp.read(), reason='temp blob for vs'
                        ))

            if self.config.verbose_vs:
                emote_sequence = VERBOSE_VS_JOINER.join(
                    [f"{i}\N{COMBINING ENCLOSING KEYCAP}{e}" for i, e in enumerate(temp_emotes, 1)]
                )
            else:
                emote_sequence = COMPACT_VS_JOINER.join(map(str, temp_emotes))

            decision = await ctx.confirm(
                f"It will look like:\n\n{emote_sequence}",
                title='Create a VS vote?',
                color=discord.Colour.gold()
            )

            # Timed out or user cancelled action
            if not decision:
                for temp_emoji in temp_emotes:
                    await temp_emoji.delete()
                return

            queue = self.bot.get_channel(self.config.approval_queue)

            vs_message = await queue.send(emote_sequence)
            for index, this_emoji in enumerate(temp_emotes, 1):
                await vs_message.add_reaction(f"{index}\N{COMBINING ENCLOSING KEYCAP}")
                await this_emoji.delete()

            merge_list = []

            for this_emoji in emoji:
                suggestion = this_emoji[0]
                if not suggestion:
                    continue
                merge_list.append(f"#{suggestion.idx} had {suggestion.upvotes} upvotes, "
                                  f"{suggestion.downvotes} downvotes.")
                await suggestion.remove_from_public_queue()

            merge_format = "\n".join(merge_list)

            await ctx.send(f"Successfully created VS vote.\n{merge_format}")
            await asyncio.sleep(5)  # add extra effect to the Lock

    @commands.command()
    @is_council()
    async def status(self, ctx, suggestion: Suggestion):
        """Views the status of a submission."""
        await ctx.send(embed=suggestion.embed)
        return

    @commands.command()
    async def revoke(self, ctx):
        """User-facing: DMs the user a wizard for revoking their own suggestions."""

        # delete the message to prevent spam
        if ctx.guild:
            await ctx.message.delete()

        # fetch submissions made by this user that hasn't reached a verdict
        submissions = await ctx.bot.db.fetch(
            """
            SELECT * FROM suggestions
            WHERE user_id = $1 AND council_approved IS NULL
            """,
            ctx.author.id
        )

        async def cannot_dm():
            await ctx.send(f"{ctx.author.mention}: I can't DM you, please adjust your settings.", delete_after=5.0)

        if not submissions:
            try:
                await ctx.author.send("You have no suggestions to revoke at this time.")
            except discord.HTTPException:
                await cannot_dm()
            return

        picker = discord.Embed(title='Submissions')
        picker.description = '\n'.join([
            f'{index+1}: {r["emoji_name"]} (submitted {r["submission_time"]})' for index, r in enumerate(submissions)
        ])

        command = 'Please pick a suggestion to revoke by sending its number.'
        try:
            await ctx.author.send(command, embed=picker)
        except discord.HTTPException:
            await cannot_dm()
            return

        def check(msg):
            return not msg.guild and msg.author.id == ctx.author.id

        tries = 0
        chosen = None
        while True:
            if tries == 3:
                await ctx.author.send('I give up!')
                return

            message = await ctx.bot.wait_for('message', check=check)

            try:
                index = int(message.content)
            except ValueError:
                await ctx.author.send(f'Invalid number. {command}')
                tries += 1
                continue

            if index > len(submissions) or index < 1:
                await ctx.author.send(f'Invalid choice. {command}')
                tries += 1
                continue

            chosen = submissions[index - 1]
            break

        suggestion = Suggestion(chosen)
        await suggestion.deny(
            who=ctx.author.id,
            reason='Manually revoked',
            revoke=True
        )
        await ctx.author.send('Suggestion has been revoked.')

    @commands.command()
    @is_council()
    async def show(self, ctx, suggestion: Suggestion):
        """Show a suggestion's emoji."""
        embed = discord.Embed(title=f'Suggestion {suggestion.idx}')
        embed.set_image(url=suggestion.emoji_url)
        await ctx.send(embed=embed)

    @staticmethod
    def generate_test_frame(emoji_image: Image.Image):
        max_dimension = max(emoji_image.size)
        scalar = 128 / max_dimension
        new_sizing = int(emoji_image.width * scalar), int(emoji_image.height * scalar)
        placement = (128 - new_sizing[0]) >> 1, (128 - new_sizing[1]) >> 1

        with Image.new("RGBA", (128, 128), (0, 0, 0, 0)) as bounding:
            normalized = emoji_image.convert("RGBA").resize(new_sizing, Image.ANTIALIAS)
            bounding.paste(normalized, placement, mask=normalized)

            larger = bounding.resize((64, 64), Image.ANTIALIAS)
            smaller = bounding.resize((44, 44), Image.ANTIALIAS)

        background_im = Image.open(path.join(path.dirname(__file__), "test_base.png"))

        background_im.paste(smaller, (346, 68), mask=smaller)
        background_im.paste(larger, (137, 169), mask=larger)

        background_im.paste(smaller, (348, 331), mask=smaller)
        background_im.paste(larger, (139, 432), mask=larger)

        return background_im.resize((410, 259), Image.ANTIALIAS)

    def test_backend(self, emoji_image: Image.Image):
        """Produce theme testing image for a given emoji."""
        logger.info("Producing a test image...")
        buffer = BytesIO()

        frame_listing = []

        interval = emoji_image.info.get("duration")

        for _ in range(600):  # never render more than 600 frames
            frame_listing.append(self.generate_test_frame(emoji_image))

            try:
                emoji_image.seek(emoji_image.tell() + 1)
            except EOFError:
                break

        initial_frame = frame_listing.pop(0)

        if frame_listing:
            initial_frame.save(buffer, "gif", duration=interval, save_all=True, append_images=frame_listing, loop=0)
            buffer.seek(0)
            return discord.File(filename="test.gif", fp=buffer)
        else:
            initial_frame.save(buffer, "png")
            buffer.seek(0)
            return discord.File(filename="test.png", fp=buffer)

    @commands.command()
    @is_council_or_cooldown(1, 60, commands.BucketType.user)
    async def test(self, ctx, suggestion: PartialSuggestionConverter=None):
        """Test a suggestion's appearance on dark and light themes."""

        if suggestion is None:
            if ctx.message.attachments and ctx.message.attachments[0].proxy_url:
                suggestion = (None, ctx.message.attachments[0].proxy_url)
            else:
                raise commands.BadArgument("Couldn't resolve to suggestion or image.")

        async with ctx.channel.typing():

            # Download the image.
            try:
                async with ctx.bot.session.get(suggestion[1]) as resp:
                    emoji_bytes = await resp.read()
            except aiohttp.ClientError:
                await ctx.send("Couldn't download the emoji... <:blobthinkingfast:452680715755192330>")
                return

            emoji_bio = BytesIO(emoji_bytes)

            try:
                emoji_im = Image.open(emoji_bio)
            except OSError:
                await ctx.send("Unable to identify the file type of that emoji. "
                               "<:blobthinkingfast:452680715755192330>")
                return

            file = await self.bot.loop.run_in_executor(None, self.test_backend, emoji_im)
            await ctx.send(file=file)

    @commands.command(aliases=['sg'])
    @is_council()
    async def suggestions(self, ctx, limit: int=10):
        """Views recent suggestions."""

        if limit > 200:
            await ctx.send(f'{limit} suggestions is a bit much. 200 is the maximum.')
            return

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
                str(s.idx), ':' + s.record['emoji_name'] + ':', submitted_by,
                f'▲ {s.record["upvotes"]} / ▼ {s.record["downvotes"]}',
                status
            )

        paginator = commands.Paginator()
        for line in (await table.render(ctx.bot.loop)).split('\n'):
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)

    @commands.command(aliases=["vi"])
    @is_council()
    async def vote_info(self, ctx, which: int):
        """Views voting info by suggestion or user ID"""

        vote_records = await self.db.fetch("""
            SELECT * FROM council_votes
            WHERE $1::BIGINT IN (suggestion_index::BIGINT, user_id) AND TRUE IN (has_approved, has_denied)
            ORDER BY vote_time DESC
            LIMIT 20
        """, which)

        table = Table('#', 'User', 'Vote', 'When')
        for record in vote_records:
            suggestion_id = record['suggestion_index']

            user = ctx.bot.get_user(record['user_id'])
            voted_by = f'{user} {user.id}' if user else str(record['user_id'])

            approve = record['has_approved']
            deny = record['has_denied']

            vote = "Both" if approve and deny else ("Yes" if approve else "No")

            when = record["vote_time"].strftime("%Y-%m-%d %H:%M:%S UTC")

            table.add_row(
                str(suggestion_id), voted_by, vote, when
            )

        paginator = commands.Paginator()
        for line in (await table.render(ctx.bot.loop)).split('\n'):
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)
