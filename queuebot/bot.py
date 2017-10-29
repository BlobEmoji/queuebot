from discord.ext import commands


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Not really needed.
        self.remove_command('help')
