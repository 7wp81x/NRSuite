"""Explicit plugin loading for NRSuite."""

import importlib.util
import os
import sys

from .plugin_api import PluginAPI
from .ui import log


class PluginManager:
    def __init__(self, registry, hooks, log_func=None):
        self.registry = registry
        self.hooks = hooks
        self.log = log_func or log
        self.loaded = []

    def load_paths(self, paths) -> list:
        loaded = []
        for path in paths or []:
            loaded.extend(self.load_path(path))
        return loaded

    def load_path(self, path: str) -> list:
        if os.path.isdir(path):
            return self.load_directory(path)
        return [self.load_file(path)]

    def load_directory(self, directory: str) -> list:
        loaded = []
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".py") or name.startswith("_"):
                continue
            loaded.extend(self.load_file(os.path.join(directory, name)))
        return loaded

    def load_file(self, path: str) -> list:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(f"nrsuite_plugin_{name}", path)
        module = importlib.util.module_from_spec(spec)
        parent = os.path.dirname(path)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        spec.loader.exec_module(module)

        register = getattr(module, "register", None)
        if not callable(register):
            raise RuntimeError(f"plugin {path} has no register(api) function")

        api = PluginAPI(name, self.registry, self.hooks)
        register(api)
        self.loaded.append(name)
        self.log(f"Loaded plugin: {name}", level="ok")
        return [name]
