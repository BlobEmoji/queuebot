# -*- coding: utf-8 -*-

from collections import namedtuple

from queuebot import utils


def test_links():
    assert utils.clean_links("http://google.com") == "<http://google.com>"
    assert utils.clean_links("https://google.com") == "<https://google.com>"
    assert utils.clean_links("invalid://link") == "invalid://link"
    assert utils.clean_links("<https://google.com>") == r"\<<https://google.com>>"


def test_markdown():
    assert utils.clean_text("**important**") == r"\*\*important\*\*"
    assert utils.clean_text(r"C:\etc") == r"C:\\etc"

    FakeModel = namedtuple('FakeModel', 'id name')

    assert "`" not in utils.name_id(FakeModel(123, 'one ` two ` three'))


def test_timer():
    with utils.Timer() as t:
        pass

    assert t.end > t.begin
    assert t.duration > 0
    assert t.duration < 0.01

    value = round((t.end - t.begin) * 1000, 2)

    assert str(t) == f'{value}ms'
