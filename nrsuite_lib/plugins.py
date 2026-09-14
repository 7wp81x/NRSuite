"""Explicit plugin and post-script loading for NRSuite."""

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
        self.loaded_plugins = []
        self.loaded_posts = []

    def load_paths(self, paths) -> list:
        return self._load_many(paths, kind="plugin")

    def load_posts(self, paths) -> list:
        return self._load_many(paths, kind="post")

    def _load_many(self, paths, kind: str) -> list:
        loaded = []
        for path in paths or []:
            loaded.extend(self.load_path(path, kind=kind))
        return loaded

    def load_path(self, path: str, kind: str = "plugin") -> list:
        if os.path.isdir(path):
            return self.load_directory(path, kind=kind)
        return self.load_file(path, kind=kind)

    def load_directory(self, directory: str, kind: str = "plugin") -> list:
        loaded = []
        if not os.path.isdir(directory):
            return loaded
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".py") or name.startswith("_"):
                continue
            try:
                loaded.extend(self.load_file(os.path.join(directory, name), kind=kind))
            except Exception as e:
                self.log(f"Failed to load {kind} {name}: {e}", level="warn")
        return loaded

    def load_file(self, path: str, kind: str = "plugin") -> list:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(f"nrsuite_{kind}_{name}", path)
        module = importlib.util.module_from_spec(spec)
        parent = os.path.dirname(path)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        spec.loader.exec_module(module)

        register = getattr(module, "register", None)
        if not callable(register):
            raise RuntimeError(f"{kind} {path} has no register(api) function")

        api = PluginAPI(name, self.registry, self.hooks)
        register(api)

        record = {"name": name, "path": path}
        if kind == "post":
            self.loaded_posts.append(record)
        else:
            self.loaded_plugins.append(record)

        self.log(f"Loaded {kind}: {name}", level="ok")
        return [name]
