__all__ = ['Cog']


class Cog:
    def __init__(self, bot: 'queuebot.bot.Bot'):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
