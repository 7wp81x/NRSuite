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
import os
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
from .hooks import HookBus
from .plugins import PluginManager
from .post_scripts import register_builtin
from .modules import ModuleRegistry
from .config import DATA_DIR, ENTRYPOINT, PLUGIN_DIR, POST_DIR
from .session import NRSuiteSession
from .ui import C, log


_HELP = f"""\
{C.BOLD}NRSuite interactive commands:{C.RESET}
  {C.CYAN}help{C.RESET}                 Show this help
  {C.CYAN}clear / cls{C.RESET}          Clear the terminal screen
  {C.CYAN}status{C.RESET}               Show firmware STATUS response
  {C.CYAN}devices{C.RESET}              Show the shared session device
  {C.CYAN}show modules{C.RESET}         List available modules
  {C.CYAN}show plugins{C.RESET}         List loaded plugins
  {C.CYAN}show posts{C.RESET}           List post scripts
  {C.CYAN}show devices{C.RESET}         List USB devices
  {C.CYAN}show options{C.RESET}         Show current module options
  {C.CYAN}use <module>{C.RESET}         Select a module, e.g. use wifi/portal
  {C.CYAN}use device <N>{C.RESET}       Connect to a USB device
  {C.CYAN}disconnect{C.RESET}           Release the current USB device
  {C.CYAN}set <option> <value>{C.RESET} Set a module option, e.g. set channel 6
  {C.CYAN}unset <option>{C.RESET}       Clear a module option
  {C.CYAN}run{C.RESET}                  Run the current module
  {C.CYAN}back{C.RESET}                 Leave the current module

{C.BOLD}Flat one-shot commands still work:{C.RESET}
  {C.GREEN}scan{C.RESET}
  {C.GREEN}sniff [options]{C.RESET}
  {C.GREEN}deauth [options]{C.RESET}
  {C.GREEN}beacon [options]{C.RESET}
  {C.GREEN}portal [options]{C.RESET}
  {C.GREEN}ble ...{C.RESET}
  {C.GREEN}masstorage ...{C.RESET}
  {C.GREEN}badusb ...{C.RESET}
  {C.GREEN}exit / quit{C.RESET}          Leave interpreter mode

{C.BOLD}Examples:{C.RESET}
  {C.GREEN}use wifi/sniff{C.RESET}
  {C.GREEN}set channel 6{C.RESET}
  {C.GREEN}set hop true{C.RESET}
  {C.GREEN}run{C.RESET}
  {C.GREEN}back{C.RESET}

  {C.GREEN}use wifi/portal{C.RESET}
  {C.GREEN}show options{C.RESET}
  {C.GREEN}set action start{C.RESET}
  {C.GREEN}set ssid Test{C.RESET}
  {C.GREEN}run{C.RESET}
"""


class NRSuiteInterpreter(cmd.Cmd):
    """Foreground command loop over a single shared USB session."""

    def __init__(self, session: NRSuiteSession):
        super().__init__()
        self.session = session
        self.registry = ModuleRegistry()
        self.hooks = HookBus(on_error=self._hook_error)
        self.plugin_manager = PluginManager(self.registry, self.hooks)
        self.plugin_paths = []
        self.post_script = None
        register_builtin(self.registry)
        self.intro = (
            f"NRSuite interactive mode"
            f"{f' ({session.chip})' if session.chip else ''}."
            " Type 'help' for commands or 'exit' to quit."
        )

    def _hook_error(self, event, exc):
        self.stdout.write(f"{C.RED}[x] Hook error in {event}: {exc}{C.RESET}\n")

    def load_plugins(self, paths) -> None:
        self.plugin_paths = list(paths or [])
        errors = []

        if self.plugin_paths:
            try:
                self.plugin_manager.load_paths(self.plugin_paths)
            except Exception as e:
                errors.append(str(e))

        for directory, loader in (
            (PLUGIN_DIR, self.plugin_manager.load_paths),
            (POST_DIR, self.plugin_manager.load_posts),
        ):
            if os.path.isdir(directory):
                try:
                    loader([directory])
                except Exception as e:
                    errors.append(f"{directory}: {e}")

        plugins = [p["name"] for p in self.plugin_manager.loaded_plugins]
        posts = [p["name"] for p in self.plugin_manager.loaded_posts]
        if plugins:
            self.stdout.write(
                f"{C.GREEN}[+] Loaded plugins: {', '.join(plugins)}{C.RESET}\n"
            )
        if posts:
            self.stdout.write(
                f"{C.GREEN}[+] Loaded posts: {', '.join(posts)}{C.RESET}\n"
            )
        for error in errors:
            self.stdout.write(f"{C.RED}[x] Plugin load failed: {error}{C.RESET}\n")

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
            total = len(self.registry.modules)
            if prefix:
                self.stdout.write(
                    f"{C.CYAN}[*] {len(modules)} matching of {total} modules loaded{C.RESET}\n"
                )
            else:
                self.stdout.write(f"{C.CYAN}[*] {total} modules loaded{C.RESET}\n")
            if not modules:
                self.stdout.write("[!] No matching modules.\n")
            else:
                for module in modules:
                    self.stdout.write(
                        f"  {C.CYAN}{module.name:<20}{C.RESET} {module.description}\n"
                    )
            return False

        if what == "plugins":
            records = self.plugin_manager.loaded_plugins
            self.stdout.write(f"{C.CYAN}[*] {len(records)} plugin(s) loaded{C.RESET}\n")
            if not records:
                self.stdout.write(
                    "  Use --plugin PATH or place files in ~/.config/nrsuite/plugins\n"
                )
            for record in records:
                self.stdout.write(
                    f"  {C.CYAN}{record['name']:<20}{C.RESET} {record['path']}\n"
                )
            return False

        if what in ("posts", "post"):
            posts = self.registry.post_scripts
            self.stdout.write(
                f"{C.CYAN}[*] {len(posts)} post script(s) loaded{C.RESET}\n"
            )
            for name in sorted(posts):
                entry = posts[name]
                self.stdout.write(
                    f"  {C.CYAN}{name:<28}{C.RESET} "
                    f"{entry.get('description', '')} "
                    f"[{entry.get('source', 'builtin')}]\n"
                )
            return False

        if what in ("options", "option"):
            if self.registry.current is None:
                self.stdout.write("[!] No module selected. Use 'use <module>' first.\n")
            else:
                self.stdout.write(f"Module: {self.registry.current.name}\n")
                self.stdout.write(self.registry.current.options_text(self.registry.values) + "\n")
                self.stdout.write(f"  {'pscript':<16} current={self.post_script!r}\n")
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
        if name.lower() in ("pscript", "post", "post_script"):
            if self.registry.current is None:
                self.stdout.write("[!] Select a module before setting a post script.\n")
                return False
            self.post_script = raw.strip()
            self.stdout.write(f"{C.GREEN}[+] pscript => {self.post_script!r}{C.RESET}\n")
            return False
        ok, message = self.registry.set_value(name, raw)
        color = C.GREEN if ok else C.YELLOW
        self.stdout.write((f"{color}[+] " if ok else f"{color}[!] ") + message + f"{C.RESET}\n")
        return False

    def _cmd_unset(self, args) -> bool:
        if not args:
            self.stdout.write("[!] Usage: unset <option>\n")
            return False
        if args[0].lower() in ("pscript", "post", "post_script"):
            self.post_script = None
            self.stdout.write(f"{C.GREEN}[+] unset pscript{C.RESET}\n")
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
        plugin_args = "".join(
            f" --plugin {shlex.quote(path)}" for path in self.plugin_paths
        )
        cmd = f"env NRSUITE_CHILD=1 python {ENTRYPOINT} interact{plugin_args}"
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

    def _capture_files(self) -> set:
        try:
            return {
                os.path.join(DATA_DIR, name)
                for name in os.listdir(DATA_DIR)
                if name.endswith(".pcap")
            }
        except Exception:
            return set()

    def _collect_capture_files(self, values, before: set) -> list:
        files = []
        output = values.get("output")
        if output and output != "-":
            files.append(output)
        for path in sorted(self._capture_files() - before):
            if path not in files:
                files.append(path)
        return files

    def _run_post_script(self, context) -> None:
        if not self.post_script:
            return
        entry = self.registry.post_scripts.get(self.post_script)
        if not entry:
            self.stdout.write(
                f"{C.YELLOW}[!] Unknown post script: {self.post_script}{C.RESET}\n"
            )
            return
        try:
            result = entry["handler"](context)
        except Exception as e:
            context["post_result"] = {"ok": False, "error": str(e)}
            self.stdout.write(f"{C.RED}[x] Post script failed: {e}{C.RESET}\n")
            return

        context["post_result"] = result
        self.stdout.write(f"{C.CYAN}[*] Post script {self.post_script}:{C.RESET}\n")
        self._write_post_result(result)

    def _write_post_result(self, result) -> None:
        if isinstance(result, dict):
            for key, value in result.items():
                label = str(key).replace("_", " ").strip().title()
                if str(key).lower() == "ok" and value is True:
                    color = C.GREEN
                    tag = "[+]"
                elif str(key).lower() in ("error", "msg") and value:
                    color = C.RED
                    tag = "[x]"
                else:
                    color = C.GREEN
                    tag = "[+]"
                self.stdout.write(f"{color}{tag} {label}: {value}{C.RESET}\n")
        elif result is None:
            self.stdout.write(f"{C.GREEN}[+] ok: True{C.RESET}\n")
        else:
            self.stdout.write(f"{C.GREEN}[+] {result}{C.RESET}\n")

    def _cmd_run(self) -> bool:
        module = self.registry.current
        if module is None:
            self.stdout.write("[!] No module selected. Use 'use <module>' first.\n")
            return False

        base_context = {
            "module": module.name,
            "values": dict(self.registry.values),
            "argv": None,
            "args": None,
            "files": [],
            "session": self.session,
            "hooks": self.hooks,
        }

        # Plugin modules are invoked directly with the context object.
        if getattr(module, "handler", None):
            self.hooks.emit("pre_module", **base_context)
            try:
                result = module.handler(base_context)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            base_context["result"] = result
            self._run_post_script(base_context)
            self.hooks.emit("post_module", **base_context)
            return bool(result and result.get("stop"))

        try:
            argv = self.registry.build()
        except Exception as e:
            self.stdout.write(f"{C.RED}[!] {e}{C.RESET}\n")
            return False

        try:
            args = self.registry.parse(argv)
        except SystemExit:
            return False

        before_files = self._capture_files()
        context = dict(base_context)
        context["argv"] = argv
        context["args"] = vars(args)

        self.hooks.emit("pre_module", **context)
        self.stdout.write(f"{C.CYAN}[*] Running: {' '.join(argv)}{C.RESET}\n")
        stop = self._dispatch(args)
        context["result"] = {"ok": True, "stop": stop}
        context["files"] = self._collect_capture_files(self.registry.values, before_files)
        self._run_post_script(context)
        self.hooks.emit("post_module", **context)
        return stop

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


def run_interpreter(fd=None, auto_connect: bool = True, plugin_paths=None) -> int:
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
    interp.load_plugins(plugin_paths or [])
    try:
        interp.cmdloop()
    except KeyboardInterrupt:
        interp.stdout.write("\n")
    finally:
        session.close()
    return 0
