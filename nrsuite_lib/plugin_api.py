"""Public API exposed to user plugins."""

from .ui import log as ui_log


class PluginAPI:
    """API object passed to a plugin's register(api) function."""

    def __init__(self, plugin_name, registry, hooks, log_func=None):
        self.plugin_name = plugin_name
        self.registry = registry
        self.hooks = hooks
        self.log = log_func or ui_log

    def on(self, event: str, callback):
        """Register a hook callback(event_name, payload)."""
        self.hooks.on(event, callback)
        return callback

    def register_module(self, name: str, handler, description: str = "") -> str:
        """Register an interactive module, exposed as plug/<name>."""
        full_name = self.registry.register_dynamic(name, description, handler)
        return full_name

    def register_post(self, name: str, handler, description: str = "") -> str:
        """Register a post script, e.g. post/wifi/count_packet."""
        self.registry.register_post(name, handler, description)
        return name

    def emit(self, event: str, **payload) -> None:
        self.hooks.emit(event, **payload)
