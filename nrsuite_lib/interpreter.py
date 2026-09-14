"""Interactive foreground interpreter for NRSuite.

Usage:
    ./nrsuite --interact
    ./nrsuite interact

The shell keeps one NRSuiteSession open and reuses it for each foreground
command. Background jobs and plugins are intentionally out of scope for this
first version.
"""

import cmd
import difflib
import json
import shlex

from .cli import build_parser
from .commands import (
    do_badusb,
    do_beacon,
    do_ble_badble,
    do_ble_keyboard,
    do_deauth,
    do_masstorage,
    do_portal,
    do_scan,
    do_sniff,
)
from .devices import _enumerate_usb_paths, _launch_with_fd_tty, do_list_devices
from .espbridge_compat import describe_device, detect_backend
from .modules import ModuleRegistry
from .config import ENTRYPOINT
from .session import NRSuiteSession
from .ui import C, log


_HELP = """\
NRSuite interactive commands:
  help                 Show this help
  clear / cls          Clear the terminal screen
  status               Show firmware STATUS response
  devices              Show the shared session device
  show modules         List available modules
  show devices         List USB devices
  show options         Show current module options
  use <module>         Select a module, e.g. use wifi/portal
  use device <N>       Connect to a USB device
  disconnect           Release the current USB device
  set <option> <value> Set a module option, e.g. set channel 6
  unset <option>       Clear a module option
  run                  Run the current module
  back                 Leave the current module

Flat one-shot commands still work:
  scan
  sniff [options]
  deauth [options]
  beacon [options]
  portal [options]
  ble ...
  masstorage ...
  badusb ...
  exit / quit          Leave interpreter mode

Examples:
  use wifi/sniff
  set channel 6
  set hop true
  run
  back

  use wifi/portal
  show options
  set action start
  set ssid Test
  run
"""


class NRSuiteInterpreter(cmd.Cmd):
    """Foreground command loop over a single shared USB session."""

    def __init__(self, session: NRSuiteSession):
        super().__init__()
        self.session = session
        self.registry = ModuleRegistry()
        self.intro = (
            f"NRSuite interactive mode"
            f"{f' ({session.chip})' if session.chip else ''}."
            " Type 'help' for commands or 'exit' to quit."
        )

    @property
    def prompt(self):
        label = "(nrsuite"
        if self.session.chip:
            label += f":{self.session.chip}"
        elif self.session.alive:
            label += ":connected"
        if self.registry.current:
            label += f":{self.registry.current.name}"
        return f"{C.CYAN}{label}){C.RESET} > "

    def preloop(self):
        try:
            import readline
            readline.set_history_length(1000)
        except Exception:
            pass

    def emptyline(self):
        return False

    def do_help(self, arg):
        topic = arg.strip().lower()
        if not topic:
            self.stdout.write(_HELP)
            return False

        module_names = sorted(self.registry.modules)
        flat_commands = [
            "devices", "scan", "sniff", "deauth", "beacon",
            "portal", "ble", "masstorage", "badusb", "interact",
        ]

        if topic in self.registry.modules:
            module = self.registry.modules[topic]
            self.stdout.write(f"{C.CYAN}{module.name}{C.RESET} - {module.description}\n")
            self.stdout.write(module.options_text({}) + "\n")
            return False

        group_matches = [n for n in module_names if n.startswith(topic + "/")]
        if group_matches:
            self.stdout.write(f"{C.CYAN}{topic}{C.RESET} modules:\n")
            for name in group_matches:
                module = self.registry.modules[name]
                self.stdout.write(f"  {C.CYAN}{name:<20}{C.RESET} {module.description}\n")
            return False

        all_names = module_names + flat_commands + sorted({n.split('/')[0] for n in module_names})
        matches = difflib.get_close_matches(topic, all_names, n=5, cutoff=0.45)
        if matches:
            self.stdout.write(f"[!] No exact help for '{arg}'. Did you mean:\n")
            for name in matches:
                self.stdout.write(f"  {C.CYAN}{name}{C.RESET}\n")
        else:
            self.stdout.write(f"[!] No help topic found for '{arg}'. Type 'help' for the command list.\n")
        return False

    def do_exit(self, arg):
        """Leave interpreter mode."""
        return True

    def do_quit(self, arg):
        """Leave interpreter mode."""
        return True

    def do_EOF(self, arg):
        self.stdout.write("\n")
        return True

    def do_clear(self, arg):
        """Clear the terminal screen."""
        self.stdout.write("\033[2J\033[H")
        try:
            self.stdout.flush()
        except Exception:
            pass
        return False

    do_cls = do_clear

    def do_status(self, arg):
        """Query and print firmware STATUS."""
        if not self.session.alive:
            self.stdout.write("[!] No device connected. Use 'show devices' and 'use device <N>'.\n")
            return False
        resp = self.session.send_cmd("STATUS", timeout=5)
        if resp is None:
            self.stdout.write("[!] No STATUS response from the ESP32.\n")
            return False
        self.stdout.write(json.dumps(resp, indent=2, sort_keys=True) + "\n")
        return False

    def do_devices(self, arg):
        """Show the device currently owned by this interpreter session."""
        if self.session.device is None:
            self.stdout.write("[!] No active session device.\n")
        else:
            self.stdout.write(f"[0] {describe_device(self.session.device)}  (shared session)\n")
        return False

    def default(self, line):
        line = line.strip()
        if not line:
            return False

        try:
            argv = shlex.split(line)
        except ValueError as e:
            self.stdout.write(f"[!] Could not parse command line: {e}\n")
            return False

        if argv and argv[0] in ("exit", "quit"):
            return True

        if argv and argv[0].lower() in ("clear", "cls"):
            return self.do_clear("")

        if argv and argv[0].lower() in (
            "show", "use", "set", "unset", "run", "exploit", "back", "disconnect"
        ):
            return self._handle_module_command(argv)

        known_flat = {
            "devices", "scan", "sniff", "deauth", "beacon",
            "portal", "ble", "masstorage", "badusb", "interact",
        }
        if argv and argv[0].lower() not in known_flat:
            all_names = sorted(known_flat | set(self.registry.modules))
            matches = difflib.get_close_matches(argv[0], all_names, n=5, cutoff=0.4)
            self.stdout.write(f"{C.YELLOW}[!] Command not found: {argv[0]}{C.RESET}\n")
            if matches:
                self.stdout.write(f"{C.YELLOW}[!] Did you mean: " + ", ".join(matches) + f"{C.RESET}\n")
            self.stdout.write("[!] Type 'help' to list commands.\n")
            return False

        parser = build_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return False

        if args.command == "interact":
            self.stdout.write("[*] Already in interactive mode.\n")
            return False

        return self._dispatch(args)

    def _handle_module_command(self, argv) -> bool:
        command = argv[0].lower()
        args = argv[1:]
        if command == "show":
            return self._cmd_show(args)
        if command == "use":
            return self._cmd_use(args)
        if command == "set":
            return self._cmd_set(args)
        if command == "unset":
            return self._cmd_unset(args)
        if command == "disconnect":
            return self._cmd_disconnect()
        if command == "back":
            return self._cmd_back()
        if command in ("run", "exploit"):
            return self._cmd_run()
        return False

    def _cmd_show(self, args) -> bool:
        what = args[0].lower() if args else "modules"
        if what == "modules":
            prefix = args[1] if len(args) > 1 else None
            modules = self.registry.list_modules(prefix)
            if not modules:
                self.stdout.write("[!] No matching modules.\n")
            else:
                for module in modules:
                    self.stdout.write(f"  {C.CYAN}{module.name:<20}{C.RESET} {module.description}\n")
            return False
        if what in ("options", "option"):
            if self.registry.current is None:
                self.stdout.write("[!] No module selected. Use 'use <module>' first.\n")
            else:
                self.stdout.write(f"Module: {self.registry.current.name}\n")
                self.stdout.write(self.registry.current.options_text(self.registry.values) + "\n")
            return False
        if what == "status":
            return self.do_status("")
        if what in ("devices", "device"):
            return self._show_devices()
        self.stdout.write(f"[!] Unknown show target: {what}\n")
        return False

    def _cmd_use(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: use <module> | use device <N>\n")
            return False
        if args[0].lower() == "device":
            return self._use_device(args[1:])
        ok, message = self.registry.use(args[0])
        color = C.GREEN if ok else C.YELLOW
        self.stdout.write((f"{color}[+] " if ok else f"{color}[!] ") + message + f"{C.RESET}\n")
        return False

    def _cmd_set(self, args) -> bool:
        if len(args) < 2:
            self.stdout.write("[!] Usage: set <option> <value>\n")
            return False
        name = args[0]
        raw = " ".join(args[1:])
        ok, message = self.registry.set_value(name, raw)
        color = C.GREEN if ok else C.YELLOW
        self.stdout.write((f"{color}[+] " if ok else f"{color}[!] ") + message + f"{C.RESET}\n")
        return False

    def _cmd_unset(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: unset <option>\n")
            return False
        ok, message = self.registry.unset_value(args[0])
        color = C.GREEN if ok else C.YELLOW
        self.stdout.write((f"{color}[+] " if ok else f"{color}[!] ") + message + f"{C.RESET}\n")
        return False

    def _show_devices(self) -> bool:
        paths = _enumerate_usb_paths()
        if not paths:
            do_list_devices()
            return False
        self.stdout.write("[*] USB devices:\n")
        for i, path in enumerate(paths):
            self.stdout.write(f"  {C.CYAN}[{i}]{C.RESET} {path}\n")
        if self.session.alive:
            self.stdout.write(f"[*] Connected session: {self.session.chip or 'device active'}\n")
        return False

    def _resolve_device_spec(self, spec: str, paths: list) -> str:
        spec = spec.strip()
        if spec.isdigit():
            idx = int(spec)
            if not paths:
                raise ValueError("No USB devices found to index.")
            if idx < 0 or idx >= len(paths):
                raise ValueError(f"Device index {idx} out of range.")
            return paths[idx]
        if paths and spec in paths:
            return spec
        if spec.startswith("/dev/"):
            return spec
        matches = [p for p in paths if spec in p]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous device spec: {spec}")
        if paths:
            raise ValueError(f"No device matching {spec!r}.")
        raise ValueError(f"No USB devices found for {spec!r}.")

    def _use_device(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: use device <N|path>\n")
            return self._show_devices()
        if self.session.alive:
            self.stdout.write("[!] Already connected. Use 'disconnect' first.\n")
            return False

        try:
            backend = detect_backend()
        except Exception as e:
            self.stdout.write(f"[!] {e}\n")
            return False

        if backend == "root":
            self.stdout.write("[*] Root backend attaches to the first matching USB device.\n")
            try:
                self.session.open()
            except Exception as e:
                self.stdout.write(f"[x] Failed to connect: {e}\n")
                return False
            self.stdout.write(f"[+] Connected to {self.session.chip or 'device'}.\n")
            return False

        try:
            paths = _enumerate_usb_paths()
            device_path = self._resolve_device_spec(args[0], paths)
        except Exception as e:
            self.stdout.write(f"[!] {e}\n")
            return False

        self.stdout.write(f"[*] Connecting to {device_path}...\n")
        cmd = f"env NRSUITE_CHILD=1 python {ENTRYPOINT} interact"
        try:
            _launch_with_fd_tty(device_path, cmd)
        except KeyboardInterrupt:
            self.stdout.write("\n[!] Connection cancelled.\n")
        except Exception as e:
            self.stdout.write(f"[x] Failed to connect: {e}\n")
        return False

    def _cmd_disconnect(self) -> bool:
        if not self.session.alive:
            self.stdout.write("[!] Not connected.\n")
            return False
        self.session.close()
        self.stdout.write("[+] Disconnected.\n")
        return False

    def _cmd_back(self) -> bool:
        if self.registry.current is None:
            self.stdout.write("[!] No module selected.\n")
        else:
            name = self.registry.current.name
            self.registry.current = None
            self.registry.values = {}
            self.stdout.write(f"{C.GREEN}[+] Left module {name}{C.RESET}\n")
        return False

    def _cmd_run(self) -> bool:
        if self.registry.current is None:
            self.stdout.write("[!] No module selected. Use 'use <module>' first.\n")
            return False

        try:
            argv = self.registry.build()
        except Exception as e:
            self.stdout.write(f"[!] {e}\n")
            return False

        self.stdout.write(f"{C.CYAN}[*] Running: {' '.join(argv)}{C.RESET}\n")
        try:
            args = self.registry.parse(argv)
        except SystemExit:
            return False
        return self._dispatch(args)

    def _dispatch(self, args) -> bool:
        if args.command == "devices":
            return self._show_devices()
        if not self.session.alive:
            self.stdout.write(
                "[!] No device connected. Use 'show devices' and 'use device <N>'.\n"
            )
            return False

        self.session.begin_command()
        self.session.activate()
        invalidates_session = False

        try:
            if args.command == "scan":
                do_scan()
            elif args.command == "sniff":
                do_sniff(args=args)
            elif args.command == "deauth":
                do_deauth(args=args)
            elif args.command == "beacon":
                do_beacon(args=args)
            elif args.command == "portal":
                do_portal(args=args)
            elif args.command == "ble":
                if args.ble_action == "badble":
                    do_ble_badble(args=args)
                elif args.ble_action == "keyboard":
                    do_ble_keyboard(args=args)
            elif args.command == "masstorage":
                do_masstorage(args=args)
                invalidates_session = (args.msc_action == "start")
            elif args.command == "badusb":
                do_badusb(args=args)
                invalidates_session = True
            else:
                self.stdout.write(f"[!] Unsupported command: {args.command}\n")
        except KeyboardInterrupt:
            self.stdout.write("\n[!] Command interrupted.\n")
        except Exception as e:
            self.stdout.write(f"[x] Command failed: {e}\n")
        finally:
            self.session.deactivate()

        if invalidates_session:
            self.stdout.write(
                "[!] That command re-enumerates or disconnects the USB link; "
                "exiting interpreter mode. Reconnect and start again.\n"
            )
            return True

        return False


def run_interpreter(fd=None, auto_connect: bool = True) -> int:
    """Open a shared session and run the foreground interpreter.

    auto_connect=False starts disconnected and lists available devices so the
    user can pick one with ``use device <N>``.
    """
    session = NRSuiteSession(fd)
    if auto_connect:
        try:
            session.open()
        except Exception as e:
            log(f"Failed to open interpreter session: {e}", C.RED, level="err")
            return 1
    else:
        do_list_devices()

    interp = NRSuiteInterpreter(session)
    try:
        interp.cmdloop()
    except KeyboardInterrupt:
        interp.stdout.write("\n")
    finally:
        session.close()
    return 0
