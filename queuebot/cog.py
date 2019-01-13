__all__ = ['Cog']


class Cog:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
