# -*- coding: utf-8 -*-
import logging
import sys
from time import sleep

import config
from queuebot.bot import Queuebot

# wait for postgres to start
sleep(2)

logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('queuebot').setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
handler = logging.FileHandler(filename='queuebot.log', encoding='utf-8', mode='a')
handler.setFormatter(formatter)
stream = logging.StreamHandler(stream=sys.stdout)
stream.setFormatter(formatter)

logging.getLogger().addHandler(handler)  # Log everything to queuebot.log.
logging.getLogger().addHandler(stream)   # Log everything to stdout.

bot = Queuebot(command_prefix='q!')
bot.discover_exts('queuebot/cogs')
bot.run(config.token)
