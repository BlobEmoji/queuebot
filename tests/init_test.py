# -*- coding: utf-8 -*-

import asyncio
import datetime
import os

import asyncpg
import discord
from discord import raw_models

from queuebot.bot import Queuebot
from queuebot.config import config_from_file

if os.name != "nt":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def main():
    config = config_from_file("config.yaml")

    assert config.get("pg_credentials")
    assert config.get("pg_credentials") == config.pg_credentials

    db = await asyncpg.create_pool(**config.pg_credentials)

    bot = Queuebot(command_prefix='q!', config=config, db=db)

    bot.discover_exts('queuebot/cogs')

    # imaginary login
    bot._connection.user = discord.ClientUser(state=bot._connection, data={
        "username": "QueueBot",
        "id": "210987654321098765",
        "discriminator": 1337,
        "avatar": None,
        "bot": True
    })

    record = await bot.db.fetchrow(
        """
        INSERT INTO suggestions (
            user_id,
            council_message_id,
            emoji_id,
            emoji_name,
            submission_time,
            suggestions_message_id,
            emoji_animated
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7
        )
        RETURNING idx
        """,
        122122926760656896,
        294924538062569492,
        396521731440771085,
        "blobsmile",
        datetime.datetime.utcnow(),
        312640412474933248,
        False
    )

    idx = record["idx"]
    assert idx
    from queuebot.cogs.queue.suggestion import Suggestion

    suggestion = await Suggestion.get_from_id(idx)

    assert repr(suggestion) == \
        f"<Suggestion idx={idx} user_id=122122926760656896 upvotes=0 downvotes=0>"

    queuecog = bot.get_cog("BlobQueue")

    approve_name, approve_id = config.approve_emoji.split(':')
    event = raw_models.RawReactionActionEvent({
        'message_id': 294924538062569492,
        'channel_id': config.council_queue,
        'user_id': 69198249432449024,
    }, discord.PartialEmoji(animated=False, name=approve_name, id=int(approve_id)))

    await queuecog.on_raw_reaction_add(event)

    await suggestion.update_inplace()

    assert repr(suggestion) == \
        f"<Suggestion idx={idx} user_id=122122926760656896 upvotes=1 downvotes=0>"

    await bot.close()


def test_virtual_queue():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
