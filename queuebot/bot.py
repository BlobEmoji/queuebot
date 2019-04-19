import datetime
import logging
import typing
from pathlib import Path

import aiohttp
import discord
from asyncpg.pool import Pool
from discord.ext import commands

from queuebot.context import Context

logger = logging.getLogger(__name__)


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #: OAuth2 application owner.
        self.owner: discord.User = None

        #: List of extension names to load. We store this because `self.extensions` is volatile during reload.
        self.to_load: typing.List[str] = None

        self.config = kwargs.pop('config')

        # Database connection to PostgreSQL
        self.db: Pool = kwargs.pop('db')

        self.session = aiohttp.ClientSession(loop=self.loop)

    @property
    def council_roles(self):
        return set(self.config.get('council_roles', []))

    @property
    def blob_emoji(self) -> discord.Guild:
        suggestions_channel = self.get_channel(self.config.suggestions_channel)
        if suggestions_channel is None:
            return None
        return suggestions_channel.guild

    def tick(self, variant: bool = True, *, id: bool = False) -> typing.Union[int, discord.Emoji]:
        if variant:
            emoji_id = self.config.approve_emoji_id
        else:
            emoji_id = self.config.deny_emoji_id

        if id:
            return emoji_id

        return self.get_emoji(emoji_id)

    async def close(self):
        logger.info('Closing.')
        await super().close()
        await self.db.close()
        await self.session.close()

    async def on_ready(self):
        # Grab owner from application info.
        if not self.owner:
            self.owner = (await self.application_info()).owner

        logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    async def log(self, content, **kwargs) -> typing.Optional[discord.Message]:
        """Log a message to the configured bot logging channel."""
        timestamp = f'`[{datetime.datetime.utcnow().strftime("%H:%M")}]`'
        channel = self.get_channel(self.config.bot_log)
        if not channel:
            return None
        return await channel.send(f'{timestamp} {content}', **kwargs)

    async def is_owner(self, user):
        if user.id in self.config.get('admins', []):
            return True
        return await super().is_owner(user)

    async def on_message(self, msg: discord.Message):
        # Ignore messages from bots.
        if msg.author.bot:
            return

        # Do not process commands until we are ready.
        await self.wait_until_ready()

        context = await self.get_context(msg, cls=Context)
        await self.invoke(context)

    def discover_exts(self, directory: str):
        """Loads all extensions from a directory."""
        ignore = {'__pycache__', '__init__'}

        exts = [
            p.stem for p in Path(directory).resolve().iterdir()
            if p.stem not in ignore
        ]

        logger.info('Loading extensions: %s', exts)

        for ext in exts:
            self.load_extension('queuebot.cogs.' + ext)

        self.to_load = list(self.extensions.keys()).copy()
        logger.info('To load: %s', self.to_load)
