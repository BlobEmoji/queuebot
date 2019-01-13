__all__ = ['Config', 'config_from_file', 'default_config']

import os

from yaml import safe_load as _safe_load

with open(os.path.join(os.path.dirname(__file__), "default_config.yaml"), "rb") as default_config_file:
    default_config = _safe_load(default_config_file)


class Config:
    __slots__ = ('_dict',)

    def __init__(self, config_dict: dict) -> None:
        self._dict = {**default_config, **config_dict}

    def __getattr__(self, item):
        return self._dict.get(item)

    def get(self, *args, **kwargs):
        return self._dict.get(*args, **kwargs)


def config_from_file(file_path: str) -> Config:
    with open(file_path, "rb") as config_file:
        config = _safe_load(config_file)

    if isinstance(config, str):
        config = {"token": config}

    return Config(config)
