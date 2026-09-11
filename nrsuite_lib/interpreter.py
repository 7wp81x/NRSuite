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
from .session import NRSuiteSession
from .ui import C, log


_HELP = """\
NRSuite interactive commands:
  help                 Show this help
  status               Show firmware STATUS response
  devices              Show the shared session device
  scan                 Scan nearby WiFi networks
  sniff [options]      Capture packets
  deauth [options]     Send deauthentication frames
  beacon [options]     Beacon spam
  portal [options]     Captive portal
  ble ...              BLE HID commands
  masstorage ...       Mass storage commands
  badusb ...           BadUSB command
  exit / quit          Leave interpreter mode

Command arguments are the same as one-shot mode. Examples:
  scan
  sniff --channel 6 -o capture.pcap
  deauth --bssid AA:BB:CC:DD:EE:FF --channel 6 --count 5
  beacon start --ssid Test --channel 6
  ble badble --payload payload.txt
"""


class NRSuiteInterpreter(cmd.Cmd):
    """Foreground command loop over a single shared USB session."""

    def __init__(self, session: NRSuiteSession):
        super().__init__()
        self.session = session
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

        parser = build_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return False

        if args.command == "interact":
            self.stdout.write("[*] Already in interactive mode.\n")
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
                do_scan(args=args)
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
