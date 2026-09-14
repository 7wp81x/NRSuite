"""MetaSploit-style module registry for the interactive interpreter.

Modules are lightweight wrappers around the existing argparse commands. The
registry discovers each module's options directly from the real CLI parser,
so one-shot mode and interpreter mode cannot drift apart.
"""

import argparse

from .cli import build_parser


MODULE_SPECS = (
    ("wifi/scan", "Scan nearby WiFi networks", ("scan",)),
    ("wifi/sniff", "Capture packets", ("sniff",)),
    ("wifi/deauth", "Send deauthentication frames", ("deauth",)),
    ("wifi/beacon", "Broadcast 802.11 beacons", ("beacon",)),
    ("wifi/portal", "Captive portal / AP mode", ("portal",)),
    ("ble/badble", "Run a DuckyScript payload over BLE", ("ble", "badble")),
    ("ble/keyboard", "Realtime BLE keyboard passthrough", ("ble", "keyboard")),
    ("storage/start", "Enter USB mass storage mode", ("masstorage", "start")),
    ("storage/files", "List files without entering MSC mode", ("masstorage", "files")),
    ("storage/delete", "Delete a file", ("masstorage", "delete")),
    ("storage/free", "Show storage usage", ("masstorage", "free")),
    ("usb/badusb", "Run a BadUSB payload", ("badusb",)),
)


def _find_subparser(parser, path):
    node = parser
    for token in path:
        subparsers = next(
            (a for a in node._actions if isinstance(a, argparse._SubParsersAction)),
            None,
        )
        if subparsers is None or token not in subparsers.choices:
            raise KeyError(f"No parser for {' '.join(path)}")
        node = subparsers.choices[token]
    return node


def _is_store_true(action) -> bool:
    return isinstance(action, argparse._StoreTrueAction)


def _is_append(action) -> bool:
    return isinstance(action, argparse._AppendAction)


class DynamicModule:
    """Module registered by a plugin, with no argparse-derived options."""

    def __init__(self, name, description, handler):
        self.name = name
        self.description = description
        self.handler = handler
        self.options = {}
        self.aliases = {}

    def display_name(self, dest):
        return dest

    def options_text(self, values):
        return "  (plugin module; no declarative options)"

    def build_argv(self, values):
        raise RuntimeError("plugin modules are invoked directly, not via argparse")


class Module:
    def __init__(self, name, description, path, parser):
        self.name = name
        self.description = description
        self.path = tuple(path)
        self.subparser = _find_subparser(parser, path)
        self.options = {}
        self.aliases = {}

        for action in self.subparser._actions:
            if action.dest in ("help",):
                continue
            if isinstance(action, argparse._SubParsersAction):
                continue
            self.options[action.dest] = action
            for opt in action.option_strings:
                self.aliases[opt.lstrip("-").lower()] = action.dest
            # Friendly alias: beacon_action -> action
            if action.dest.endswith("_action"):
                self.aliases.setdefault("action", action.dest)

    def display_name(self, dest: str) -> str:
        aliases = sorted(alias for alias, target in self.aliases.items() if target == dest)
        return aliases[0] if aliases else dest

    def parse_value(self, dest: str, raw: str):
        action = self.options[dest]
        value = raw
        if _is_store_true(action):
            lowered = raw.strip().lower()
            if lowered in ("1", "true", "yes", "on"):
                return True
            if lowered in ("0", "false", "no", "off"):
                return False
            raise ValueError(f"{dest} expects true/false")
        if action.type is not None:
            value = action.type(raw)
        if action.choices is not None and value not in action.choices:
            raise ValueError(
                f"{dest} must be one of: {', '.join(str(c) for c in action.choices)}"
            )
        if _is_append(action):
            return [value]
        return value

    def build_argv(self, values) -> list:
        argv = list(self.path)
        for dest, action in self.options.items():
            if dest not in values:
                continue
            value = values[dest]
            opt = action.option_strings[0] if action.option_strings else None

            if opt and _is_store_true(action):
                if value:
                    argv.append(opt)
                continue

            if _is_append(action):
                items = value if isinstance(value, list) else [value]
                for item in items:
                    argv.append(opt)
                    argv.append(str(item))
                continue

            if opt:
                argv.append(opt)
                argv.append(str(value))
            else:
                if isinstance(value, list):
                    argv.extend(str(item) for item in value)
                else:
                    argv.append(str(value))
        return argv

    def options_text(self, values) -> str:
        lines = []
        for dest, action in self.options.items():
            current = values.get(dest, "")
            default = "" if action.default is None else repr(action.default)
            required = " required" if action.required else ""
            choices = ""
            if action.choices:
                choices = f" choices={{{','.join(str(c) for c in action.choices)}}}"
            lines.append(
                f"  {self.display_name(dest):<16} "
                f"type={getattr(action.type, '__name__', 'str'):<6}"
                f"{required}{choices} "
                f"default={default:<8} current={current!r}  {action.help or ''}"
            )
        return "\n".join(lines) if lines else "  (no options)"


class ModuleRegistry:
    def __init__(self):
        self.parser = build_parser()
        self.modules = {
            name: Module(name, description, path, self.parser)
            for name, description, path in MODULE_SPECS
        }
        self.current = None
        self.values = {}
        self.post_scripts = {}

    def register_dynamic(self, name: str, description: str, handler) -> str:
        name = name.strip()
        if not name.startswith("plug/"):
            name = f"plug/{name}"
        self.modules[name] = DynamicModule(name, description, handler)
        return name

    def register_post(self, name: str, handler, description: str = "",
                      source: str = "builtin") -> None:
        self.post_scripts[name] = {
            "handler": handler,
            "description": description,
            "source": source,
        }

    def list_modules(self, prefix: str | None = None) -> list[Module]:
        names = sorted(self.modules)
        if prefix:
            prefix = prefix.strip().lower()
            names = [n for n in names if n == prefix or n.startswith(prefix + "/")]
        return [self.modules[n] for n in names]

    def use(self, name: str) -> tuple[bool, str]:
        name = name.strip().lower()
        if name in self.modules:
            self.current = self.modules[name]
            self.values = {}
            return True, self.current.name
        matches = self.list_modules(name)
        if matches:
            return False, "Available modules:\n" + "\n".join(
                f"  {m.name:<20} {m.description}" for m in matches
            )
        return False, f"Unknown module: {name}"

    def set_value(self, name: str, raw: str) -> tuple[bool, str]:
        if self.current is None:
            return False, "No module selected. Use 'use <module>' first."
        key = name.strip().lower()
        dest = self.current.aliases.get(key, key)
        if dest not in self.current.options:
            return False, f"Unknown option: {name}"
        try:
            value = self.current.parse_value(dest, raw)
        except Exception as e:
            return False, str(e)

        if _is_append(self.current.options[dest]):
            self.values.setdefault(dest, [])
            if not isinstance(self.values[dest], list):
                self.values[dest] = [self.values[dest]]
            self.values[dest].extend(value)
        else:
            self.values[dest] = value
        return True, f"{dest} => {self.values[dest]!r}"

    def unset_value(self, name: str) -> tuple[bool, str]:
        if self.current is None:
            return False, "No module selected."
        key = name.strip().lower()
        dest = self.current.aliases.get(key, key)
        if dest not in self.current.options:
            return False, f"Unknown option: {name}"
        self.values.pop(dest, None)
        return True, f"unset {dest}"

    def build(self):
        if self.current is None:
            raise RuntimeError("No module selected. Use 'use <module>' first.")
        return self.current.build_argv(self.values)

    def parse(self, argv):
        return self.parser.parse_args(argv)
