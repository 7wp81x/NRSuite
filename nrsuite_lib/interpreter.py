"""Interactive foreground interpreter for NRSuite.

Usage:
    ./nrsuite --interact
    ./nrsuite interact

The shell keeps one NRSuiteSession open and reuses it for each foreground
command. Background jobs and plugins are intentionally out of scope for this
first version.
"""

import cmd
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
from .espbridge_compat import describe_device
from .modules import ModuleRegistry
from .session import NRSuiteSession
from .ui import C, log


_HELP = """\
NRSuite interactive commands:
  help                 Show this help
  status               Show firmware STATUS response
  devices              Show the shared session device
  show modules         List available modules
  show options         Show current module options
  use <module>         Select a module, e.g. use wifi/portal
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
        if self.registry.current:
            label += f":{self.registry.current.name}"
        return label + ") > "

    def preloop(self):
        try:
            import readline
            readline.set_history_length(1000)
        except Exception:
            pass

    def emptyline(self):
        return False

    def do_help(self, arg):
        self.stdout.write(_HELP)

    def do_exit(self, arg):
        """Leave interpreter mode."""
        return True

    def do_quit(self, arg):
        """Leave interpreter mode."""
        return True

    def do_EOF(self, arg):
        self.stdout.write("\n")
        return True

    def do_status(self, arg):
        """Query and print firmware STATUS."""
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

        if argv and argv[0].lower() in (
            "show", "use", "set", "unset", "run", "exploit", "back"
        ):
            return self._handle_module_command(argv)

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
                    self.stdout.write(f"  {module.name:<20} {module.description}\n")
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
            return self.do_devices("")
        self.stdout.write(f"[!] Unknown show target: {what}\n")
        return False

    def _cmd_use(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: use <module>\n")
            return False
        ok, message = self.registry.use(args[0])
        self.stdout.write((("[+] " if ok else "[!] ") + message + "\n"))
        return False

    def _cmd_set(self, args) -> bool:
        if len(args) < 2:
            self.stdout.write("[!] Usage: set <option> <value>\n")
            return False
        name = args[0]
        raw = " ".join(args[1:])
        ok, message = self.registry.set_value(name, raw)
        self.stdout.write((("[+] " if ok else "[!] ") + message + "\n"))
        return False

    def _cmd_unset(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: unset <option>\n")
            return False
        ok, message = self.registry.unset_value(args[0])
        self.stdout.write((("[+] " if ok else "[!] ") + message + "\n"))
        return False

    def _cmd_back(self) -> bool:
        if self.registry.current is None:
            self.stdout.write("[!] No module selected.\n")
        else:
            name = self.registry.current.name
            self.registry.current = None
            self.registry.values = {}
            self.stdout.write(f"[+] Left module {name}\n")
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

        self.stdout.write(f"[*] Running: {' '.join(argv)}\n")
        try:
            args = self.registry.parse(argv)
        except SystemExit:
            return False
        return self._dispatch(args)

    def _dispatch(self, args) -> bool:
        self.session.begin_command()
        self.session.activate()
        invalidates_session = False

        try:
            if args.command == "devices":
                self.do_devices("")
            elif args.command == "scan":
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


def run_interpreter(fd=None) -> int:
    """Open a shared session and run the foreground interpreter."""
    session = NRSuiteSession(fd)
    try:
        session.open()
    except Exception as e:
        log(f"Failed to open interpreter session: {e}", C.RED, level="err")
        return 1

    interp = NRSuiteInterpreter(session)
    try:
        interp.cmdloop()
    except KeyboardInterrupt:
        interp.stdout.write("\n")
    finally:
        session.close()
    return 0
