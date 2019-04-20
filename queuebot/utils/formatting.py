"""Formatting utilities from Mousey (by @FrostLuma)."""
import asyncio
import functools
import re
from typing import List, Match

import discord
from discord.utils import escape_markdown

FORMATTING_RE = re.compile(r"([*_~`\\]|<h)")
LINK_RE = re.compile(r"(<?https?://\S*)")
MENTION_RE = re.compile(r"<@!?&?(\d{15,21})>|(@everyone|@here)")


def clean_links(text: str) -> str:
    """
    Stops link embedding by surrounding all links with <>.

    Links which are already escaped get escaped a second time.
    """
    def replace(match: Match) -> str:
        match = match.group()
        # for some reason discord turns <<MY_URL>> into %3CMY_URL>
        # escaping the first < stops this from happening and displays <MY_URL> properly.
        return fr'\<{match}>' if '<' in match else f'<{match}>'

    return LINK_RE.sub(replace, text)


def clean_mentions(channel: discord.TextChannel, text: str) -> str:
    """Escapes all user and role mentions which would mention someone in the specified channel."""
    def replace(match: Match) -> str:
        mention = match.group()

        if "<@&" in mention:
            role_id = int(match.groups()[0])
            role = discord.utils.get(guild.roles, id=role_id)
            if role is not None and role.mentionable:
                mention = f"@{role.name}"

        elif "<@" in mention:
            user_id = int(match.groups()[0])
            member = guild.get_member(user_id)
            if member is not None and not member.bot and channel.permissions_for(member).read_messages:
                mention = f"@{member.name}"

        if mention in ("@everyone", "@here"):
            mention = mention.replace("@", "@\N{ZERO WIDTH SPACE}")

        return mention

    guild = channel.guild
    return MENTION_RE.sub(replace, text)


def clean_text(channel: discord.TextChannel, text) -> str:
    """Utility method to clean text as often multiple methods get used."""
    return clean_mentions(channel, escape_markdown(text))


def name_id(obj) -> str:
    """
    Formats a string containing the string representation of an object and it's ID.

    To make this mod-log friendly grave accents get replaced with modifier grave accents,
    which prevents codeblocks from being breaking out.
    """
    return f'{obj} {obj.id}'.replace('\N{GRAVE ACCENT}', '\N{MODIFIER LETTER GRAVE ACCENT}')


class Table:
    def __init__(self, *column_titles: str):
        self._rows = [column_titles]
        self._widths = []

        for _, entry in enumerate(column_titles):
            self._widths.append(len(entry))

    def _update_widths(self, row: tuple):
        for index, entry in enumerate(row):
            width = len(entry)
            if width > self._widths[index]:
                self._widths[index] = width

    def add_row(self, *row: str):
        """
        Add a row to the table.

        .. note :: There's no check for the number of items entered, this may cause issues rendering if not correct.
        """
        self._rows.append(row)
        self._update_widths(row)

    def add_rows(self, *rows: List[str]):
        for row in rows:
            self.add_row(*row)

    def _render(self):
        def draw_row(row_):
            columns = []

            for index, field in enumerate(row_):
                # digits get aligned to the right
                if field.isdigit():
                    columns.append(f" {field:>{self._widths[index]}} ")
                    continue

                # regular text gets aligned to the left
                columns.append(f" {field:<{self._widths[index]}} ")

            return "|".join(columns)

        # column title is centered in the middle of each field
        title_row = "|".join(f" {field:^{self._widths[index]}} " for index, field in enumerate(self._rows[0]))
        separator_row = "+".join("-" * (width + 2) for width in self._widths)

        drawn = [title_row, separator_row]
        # remove the title row from the rows
        self._rows = self._rows[1:]

        for row in self._rows:
            row = draw_row(row)
            drawn.append(row)

        return "\n".join(drawn)

    def render(self, loop: asyncio.AbstractEventLoop = None):
        """:coro: Returns a rendered version of the table."""
        loop = loop or asyncio.get_event_loop()

        func = functools.partial(self._render)
        return loop.run_in_executor(None, func)
