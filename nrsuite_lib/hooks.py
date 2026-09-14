"""Small synchronous hook/event bus for NRSuite.

Hooks are intentionally simple and synchronous: foreground interpreter
commands run one at a time, so post-scripts and plugins do not need a
separate worker/queue yet.
"""


class HookBus:
    def __init__(self, on_error=None):
        self._hooks = {}
        self._on_error = on_error

    def on(self, event: str, callback):
        """Register callback(event_name, payload)."""
        self._hooks.setdefault(event, []).append(callback)
        return callback

    def off(self, event: str, callback) -> None:
        hooks = self._hooks.get(event, [])
        if callback in hooks:
            hooks.remove(callback)

    def emit(self, event: str, **payload) -> None:
        """Call all callbacks registered for event."""
        for callback in list(self._hooks.get(event, [])):
            try:
                callback(event, payload)
            except Exception as e:
                if self._on_error:
                    self._on_error(event, e)

    def clear(self) -> None:
        self._hooks.clear()
