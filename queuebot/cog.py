# -*- coding: utf-8 -*-
class Cog:
    def __init__(self, bot: 'queuebot.bot.Queuebot'):
        self.bot = bot
        self.db = bot.db
