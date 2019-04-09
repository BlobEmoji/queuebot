__all__ = ['Cog']


from discord.ext import commands


class Cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def config(self):
        return self.bot.config

    @property
    def db(self):
        return self.bot.db
