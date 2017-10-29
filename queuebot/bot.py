import importlib
import inspect
import logging
from pathlib import Path

from discord.ext import commands

from queuebot.cog import Cog

logger = logging.getLogger(__name__)


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove default help command.
        self.remove_command('help')

    async def on_ready(self):
        logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    def discover_exts(self, directory: str):
        """Loads all extensions from a directory."""
        IGNORE = {'__pycache__', '__init__'}

        exts = [
            p.stem for p in Path(directory).resolve().iterdir()
            if p.is_file() and p.stem not in IGNORE
        ]

        logger.info('Loading extensions: %s', exts)

        for ext in exts:
            name = 'queuebot.cogs.' + ext
            module = importlib.import_module(name)

            cogs = inspect.getmembers(
                module, predicate=lambda obj: inspect.isclass(obj) and issubclass(obj, Cog) and obj is not Cog
            )

            for name, cog in cogs:
                logger.info('Automatically adding cog: %s', cog.__name__)
                self.add_cog(cog(self))

            if hasattr(module, 'setup'):
                module.setup(self)

            self.extensions[name] = module
