class Cog:
    def __init__(self, bot: 'queuebot.bot.Queuebot'):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db
