import io
import re
import unittest
from unittest import mock

from nrsuite_lib import interpreter


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class FakeSession:
    def __init__(self, alive=True):
        self.chip = "ESP32-C3"
        self.device = object()
        self.alive = alive
        self.begin_calls = 0
        self.activate_calls = 0
        self.deactivate_calls = 0

    def begin_command(self):
        self.begin_calls += 1

    def activate(self):
        self.activate_calls += 1

    def deactivate(self):
        self.deactivate_calls += 1

    def send_cmd(self, cmd, args=None, timeout=None):
        return {"ok": True, "chip": self.chip}

    def close(self):
        self.alive = False


class InterpreterTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.interp = interpreter.NRSuiteInterpreter(self.session)
        self.interp.stdout = io.StringIO()

    def output(self):
        return self.interp.stdout.getvalue()

    def test_prompt_includes_chip(self):
        self.assertEqual(strip_ansi(self.interp.prompt), "(nrsuite:ESP32-C3) > ")

    def test_status_prints_json(self):
        result = self.interp.do_status("")
        self.assertFalse(result)
        self.assertIn('"chip": "ESP32-C3"', self.output())

    def test_exit_stops_loop(self):
        self.assertTrue(self.interp.default("exit"))
        self.assertTrue(self.interp.default("quit"))

    def test_scan_dispatches_through_session(self):
        with mock.patch.object(interpreter, "do_scan") as do_scan:
            result = self.interp.default("scan")

        self.assertFalse(result)
        do_scan.assert_called_once_with()
        self.assertEqual(self.session.begin_calls, 1)
        self.assertEqual(self.session.activate_calls, 1)
        self.assertEqual(self.session.deactivate_calls, 1)

    def test_no_session_blocks_command(self):
        self.session.alive = False
        with mock.patch.object(interpreter, "do_scan") as do_scan:
            result = self.interp.default("scan")

        self.assertFalse(result)
        do_scan.assert_not_called()
        self.assertIn("No device connected", self.output())

    def test_msc_start_invalidates_session(self):
        with mock.patch.object(interpreter, "do_masstorage") as do_masstorage:
            result = self.interp.default("masstorage start")

        self.assertTrue(result)
        do_masstorage.assert_called_once()
        self.assertIn("re-enumerates", self.output())

    def test_badusb_invalidates_session(self):
        with mock.patch.object(interpreter, "do_badusb") as do_badusb:
            result = self.interp.default("badusb --payload test.txt")

        self.assertTrue(result)
        do_badusb.assert_called_once()

    def test_module_use_set_run_dispatches(self):
        self.interp.default("use wifi/sniff")
        self.assertIn("wifi/sniff", strip_ansi(self.interp.prompt))
        self.interp.default("set channel 6")
        self.interp.default("set hop true")

        with mock.patch.object(interpreter, "do_sniff") as do_sniff:
            result = self.interp.default("run")

        self.assertFalse(result)
        do_sniff.assert_called_once()
        args = do_sniff.call_args.kwargs["args"]
        self.assertEqual(args.channel, 6)
        self.assertTrue(args.hop)

    def test_show_modules_lists_wifi(self):
        self.interp.default("show modules")
        self.assertIn("wifi/sniff", strip_ansi(self.output()))

    def test_show_devices_lists_paths(self):
        with mock.patch.object(
            interpreter, "_enumerate_usb_paths", return_value=["/dev/a", "/dev/b"]
        ):
            self.interp.default("show devices")

        output = strip_ansi(self.output())
        self.assertIn("[0] /dev/a", output)
        self.assertIn("[1] /dev/b", output)

    def test_use_device_termux_launches_connected_child(self):
        self.session.alive = False
        with mock.patch.object(interpreter, "detect_backend", return_value="termux"), \
             mock.patch.object(interpreter, "_enumerate_usb_paths", return_value=["/dev/a"]), \
             mock.patch.object(interpreter, "_launch_with_fd_tty") as launch:
            self.interp.default("use device 0")

        launch.assert_called_once()
        device_path, cmd = launch.call_args.args
        self.assertEqual(device_path, "/dev/a")
        self.assertIn("interact", cmd)

    def test_unknown_command_is_friendly(self):
        self.interp.default("list")
        output = strip_ansi(self.output())
        self.assertIn("Command not found", output)
        self.assertNotIn("usage: nrsuite", output)

    def test_help_topic(self):
        self.interp.do_help("wifi")
        output = strip_ansi(self.output())
        self.assertIn("wifi/sniff", output)

    def test_back_leaves_module(self):
        self.interp.default("use wifi/sniff")
        self.interp.default("back")
        self.assertNotIn("wifi/sniff", strip_ansi(self.interp.prompt))

    def test_clear_emits_ansi_clear(self):
        result = self.interp.default("clear")
        self.assertFalse(result)
        self.assertIn("\033[2J\033[H", self.output())

    def test_cls_alias(self):
        self.interp.default("cls")
        self.assertIn("\033[2J\033[H", self.output())


if __name__ == "__main__":
    unittest.main()
