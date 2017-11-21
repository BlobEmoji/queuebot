import importlib
import inspect
import logging
import typing
from pathlib import Path

from asyncpg.pool import Pool
import discord
from discord.ext import commands

import config
from queuebot.cog import Cog

logger = logging.getLogger(__name__)


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove default help command.
        self.remove_command('help')

        #: OAuth2 application owner.
        self.owner: discord.User = None

        #: List of extension names to load. We store this because `self.extensions` is volatile during reload.
        self.to_load: typing.List[str] = None

        # Database connection to PostgreSQL
        self.db: Pool = kwargs.pop('db')

    async def on_ready(self):
        # Grab owner from application info.
        self.owner = (await self.application_info()).owner

        logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    async def log(self, *args, **kwargs) -> typing.Union[discord.Message, None]:
        channel = self.get_channel(config.bot_log)
        if not channel:
            return None
        return await channel.send(*args, **kwargs)

    @property
    def admins(self):
        return set([self.owner.id] + getattr(config, 'admins', []))

    @property
    def council_roles(self):
        return set(getattr(config, 'council_roles', []))

    async def on_message(self, msg: discord.Message):
        # Ignore messages from bots.
        if msg.author.bot:
            return

        # Do not process commands until we are ready.
        await self.wait_until_ready()

        await self.process_commands(msg)

    def load_extension(self, name: str):
        module = importlib.import_module(name)

        # Find Cog subclasses in the module.
        cogs = inspect.getmembers(
            module, predicate=lambda obj: inspect.isclass(obj) and issubclass(obj, Cog) and obj is not Cog
        )

        # Add all Cog subclasses.
        for _, cog in cogs:
            logger.info('Automatically adding cog: %s', cog.__name__)
            self.add_cog(cog(self))

        # Call setup(), if there is one.
        if hasattr(module, 'setup'):
            module.setup(self)

        self.extensions[name] = module

    def discover_exts(self, directory: str):
        """Loads all extensions from a directory."""
        IGNORE = {'__pycache__', '__init__'}

        exts = [
            p.stem for p in Path(directory).resolve().iterdir()
            if p.is_file() and p.stem not in IGNORE
        ]

        logger.info('Loading extensions: %s', exts)

        for ext in exts:
            self.load_extension('queuebot.cogs.' + ext)

        self.to_load = list(self.extensions.keys()).copy()
        logger.info('To load: %s', self.to_load)
