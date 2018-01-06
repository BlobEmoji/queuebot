"""Various utilities."""

# Exported.
from .formatting import *  # noqa: ignore=F401
from .messages import *  # noqa: ignore=F401

# Internal imports.
from time import monotonic as _monotonic


class Timer:
    def __init__(self):
        self.begin: float = None
        self.end: float = None

    @property
    def duration(self):
        return self.end - self.begin

    def __enter__(self):
        self.begin = _monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end = _monotonic()

    def __str__(self):
        return f"{round(self.duration * 1000, 2)}ms"
