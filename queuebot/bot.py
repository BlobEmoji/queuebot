import logging
from pathlib import Path

from discord.ext import commands

logger = logging.getLogger(__name__)


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Not really needed.
        self.remove_command('help')

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
