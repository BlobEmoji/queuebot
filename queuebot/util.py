import time


class Timer:
    def __init__(self):
        self.begin: float = None
        self.end: float = None

    @property
    def duration(self):
        return self.end - self.begin

    def __enter__(self):
        self.begin = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end = time.monotonic()

    def __str__(self):
        return f"{round(self.duration * 1000, 2)}ms"
