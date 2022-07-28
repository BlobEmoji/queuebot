import asyncio
import logging
import sys

import aiohttp
import asyncpg
import discord

from queuebot.bot import Queuebot
from queuebot.config import config_from_file

try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('queuebot').setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')

handler = logging.FileHandler(filename='queuebot.log', encoding='utf-8', mode='a')
handler.setFormatter(formatter)

stream = logging.StreamHandler(stream=sys.stdout)
stream.setFormatter(formatter)

logging.getLogger().addHandler(handler)  # Log everything to queuebot.log.
logging.getLogger().addHandler(stream)   # Log everything to stdout.


async def main():
    config = config_from_file("config.yaml")
    while True:
        try:
            db = await asyncpg.create_pool(**config.pg_credentials)
        except (ConnectionRefusedError, asyncpg.CannotConnectNowError):
            logging.getLogger('run').exception('Cannot connect to Postgres, stalling:')
            await asyncio.sleep(2)
        else:
            break

    intents = discord.Intents(
        guilds=True,
        emojis=True,
        guild_messages=True,
        guild_reactions=True,
        message_content=True,
    )

    session = aiohttp.ClientSession()

    bot = Queuebot(
        command_prefix='q!',
        intents=intents,
        max_messages=None,
        config=config,
        db=db,
        session=session,
    )

    await bot.load_extension('jishaku')
    await bot.discover_exts('queuebot/cogs')

    await bot.start(config.token)


asyncio.run(main())
