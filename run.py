# -*- coding: utf-8 -*-
import logging

from discord.ext import commands

import config
from queuebot.bot import Queuebot

logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('queuebot').setLevel(logging.DEBUG)

handler = logging.FileHandler(filename='queuebot.log', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logging.getLogger().addHandler(handler)  # Log everything to queuebot.log.

bot = Queuebot(command_prefix='q!')
bot.run(config.token)
