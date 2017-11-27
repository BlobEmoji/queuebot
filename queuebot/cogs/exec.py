# -*- coding: utf-8 -*-
"""
Handy exec (eval, debug) cog. Allows you to run code on the bot during runtime. This cog is a combination of the
exec commands of other bot authors, allowing for maximum efficiency:

Credit:
    - Rapptz: https://github.com/Rapptz/RoboDanny/blob/master/cogs/repl.py#L31-L75
    - b1naryth1ef: https://github.com/b1naryth1ef/b1nb0t/blob/master/b1nb0t/plugins/util.py#L229-L266
"""

import io
import logging
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import List, TypeVar, Callable, Dict, Any

import discord
from discord import Message, HTTPException
from discord.ext import commands
from discord.ext.commands import command, Converter, Context

from queuebot.checks import is_bot_admin
from queuebot.cog import Cog

log = logging.getLogger(__name__)

IMPLICIT_RETURN_STOP_WORDS = {
    'continue', 'break', 'raise', 'yield', 'with',
    'assert', 'del', 'import', 'pass', 'return', 'from'
}


class Code(Converter):
    def __init__(self, *, wrap_code=False, strip_ticks=True, indent_width=4, implicit_return=False):
        """
        A converter that extracts code out of code blocks and inline code formatting.

        Parameters
        ----------
        wrap_code
            Specifies whether to wrap the resulting code in a function.
        strip_ticks
            Specifies whether to strip the code of formatting-related backticks.
        indent_width
            Specifies the indent width, if wrapping.
        implicit_return
            Automatically adds a return statement, when wrapping code.
        """
        self.wrap_code = wrap_code
        self.strip_ticks = strip_ticks
        self.indent_width = indent_width
        self.implicit_return = implicit_return

    async def convert(self, ctx: Context, arg: str) -> str:
        result = arg

        if self.strip_ticks:
            # remove codeblock ticks
            if result.startswith('```') and result.endswith('```'):
                result = '\n'.join(result.split('\n')[1:-1])

            # remove inline code ticks
            result = result.strip('` \n')

        if self.wrap_code:
            # wrap in a coroutine and indent
            result = 'async def _func():\n' + textwrap.indent(result, ' ' * self.indent_width)

        if self.wrap_code and self.implicit_return:
            last_line = result.splitlines()[-1]

            # if the last line isn't indented and not returning, add it
            first_word = last_line.strip().split(' ')[0]
            no_stop = all(first_word != word for word in IMPLICIT_RETURN_STOP_WORDS)
            if not last_line[4:].startswith(' ') and no_stop:
                last_line = (' ' * self.indent_width) + 'return ' + last_line[4:]

            result = '\n'.join(result.splitlines()[:-1] + [last_line])

        return result


def format_syntax_error(e: SyntaxError) -> str:
    """ Formats a SyntaxError. """
    if e.text is None:
        return '```py\n{0.__class__.__name__}: {0}\n```'.format(e)
    # display a nice arrow
    return '```py\n{0.text}{1:>{0.offset}}\n{2}: {0}```'.format(e, '^', type(e).__name__)


def create_environment(cog: 'Exec', ctx: Context) -> Dict[Any, Any]:

    async def upload(file_name: str) -> Message:
        """Shortcut to upload a file."""
        with open(file_name, 'rb') as fp:
            return await ctx.send(file=discord.File(fp))

    def better_dir(*args, **kwargs) -> List[str]:
        """dir(), but without magic methods."""
        return [n for n in dir(*args, **kwargs) if not n.endswith('__') and not n.startswith('__')]

    T = TypeVar('T')

    def grabber(lst: List[T]) -> Callable[[int], T]:
        """Returns a function that, when called, grabs an item by ID from a list of objects with an ID."""
        def _grabber_function(thing_id: int) -> T:
            return discord.utils.get(lst, id=thing_id)
        return _grabber_function

    env = {
        'bot': ctx.bot,
        'ctx': ctx,
        'msg': ctx.message,
        'guild': ctx.guild,
        'channel': ctx.channel,
        'me': ctx.message.author,
        'cog': cog,

        # modules
        'discord': discord,
        'commands': commands,
        'command': commands.command,
        'group': commands.group,

        # utilities
        '_get': discord.utils.get,
        '_find': discord.utils.find,
        '_upload': upload,
        '_send': ctx.send,

        # grabbers
        '_g': grabber(ctx.bot.guilds),
        '_u': grabber(ctx.bot.users),
        '_c': grabber(list(ctx.bot.get_all_channels())),

        # last result
        '_': cog.last_result,
        '_p': cog.previous_code,

        'dir': better_dir,
    }

    # add globals to environment
    env.update(globals())

    return env


def codeblock(code, *, lang=''):
    return f'```{lang}\n{code}\n```'


class Exec(Cog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_result = None
        self.previous_code = None

    async def execute(self, ctx: Context, code: str):
        log.info('Eval: %s', code)

        # create eval environment
        env = create_environment(self, ctx)

        # simulated stdout
        stdout = io.StringIO()

        # define the wrapped function
        try:
            exec(compile(code, '<exec>', 'exec'), env)
        except SyntaxError as e:
            # send pretty syntax errors
            return await ctx.send(format_syntax_error(e))

        # grab the defined function
        func = env['_func']

        try:
            # execute the code
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            try:
                await ctx.message.add_reaction('\N{CACTUS}')
            except HTTPException:
                pass

            # send stream and what we have
            return await ctx.send(codeblock(traceback.format_exc(limit=7), lang='py'))

        # code was good, grab stdout
        stream = stdout.getvalue()

        try:
            await ctx.message.add_reaction('\N{HIBISCUS}')
        except HTTPException:
            pass

        # set the last result, but only if it's not none
        if ret is not None:
            self.last_result = ret

        # combine simulated stdout and repr of return value
        meat = stream + repr(ret)
        message = codeblock(meat, lang='py')

        if len(message) > 2000:
            # too long
            await ctx.send('Result was too long.')
        else:
            # message was under 2k chars, just send!
            await ctx.send(message)

    @command(name='eval', aliases=['exec', 'debug'], hidden=True)
    @is_bot_admin()
    async def _eval(self, ctx: Context, *, code: Code(wrap_code=True, implicit_return=True)):
        """Executes Python code."""

        # store previous code
        self.previous_code = code

        await self.execute(ctx, code)
