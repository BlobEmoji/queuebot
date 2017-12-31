# -*- coding: utf-8 -*-

import asyncio
import asyncpg
import datetime
import os

import discord

import config
from queuebot.bot import Queuebot

if os.name != "nt":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def main():
    db = await asyncpg.create_pool(**config.pg_credentials)

    bot = Queuebot(command_prefix='q!', db=db)

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
        123456789012345678,
        234567890123456789,
        345678901234567890,
        "test",
        datetime.datetime.utcnow(),
        456789012345678901,
        False
    )

    idx = record["idx"]
    assert idx
    from queuebot.cogs.queue.suggestion import Suggestion

    suggestion = await Suggestion.get_from_id(idx)

    assert repr(suggestion) == \
        f"<Suggestion idx={idx} user_id=123456789012345678 upvotes=0 downvotes=0>"

    queuecog = bot.get_cog("BlobQueue")
    await queuecog.on_raw_reaction_add(discord.PartialReactionEmoji(name="ok", id=901234567890123456),
                                       234567890123456789, 98765432109876543, 234567890123456789)

    await suggestion.update_inplace()

    assert repr(suggestion) == \
        f"<Suggestion idx={idx} user_id=123456789012345678 upvotes=1 downvotes=0>"

    await bot.close()


def test_virtual_queue():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
