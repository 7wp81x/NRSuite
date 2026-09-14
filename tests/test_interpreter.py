import io
import unittest
from unittest import mock

from nrsuite_lib import interpreter


class FakeSession:
    def __init__(self):
        self.chip = "ESP32-C3"
        self.device = object()
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


class InterpreterTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.interp = interpreter.NRSuiteInterpreter(self.session)
        self.interp.stdout = io.StringIO()

    def test_prompt_includes_chip(self):
        self.assertEqual(self.interp.prompt, "(nrsuite:ESP32-C3) > ")

    def test_status_prints_json(self):
        result = self.interp.do_status("")
        self.assertFalse(result)
        output = self.interp.stdout.getvalue()
        self.assertIn('"chip": "ESP32-C3"', output)

    def test_exit_stops_loop(self):
        self.assertTrue(self.interp.default("exit"))
        self.assertTrue(self.interp.default("quit"))

    def test_scan_dispatches_through_session(self):
        with mock.patch.object(interpreter, "do_scan") as do_scan:
            result = self.interp.default("scan")

        self.assertFalse(result)
        do_scan.assert_called_once()
        self.assertEqual(self.session.begin_calls, 1)
        self.assertEqual(self.session.activate_calls, 1)
        self.assertEqual(self.session.deactivate_calls, 1)

    def test_msc_start_invalidates_session(self):
        with mock.patch.object(interpreter, "do_masstorage") as do_masstorage:
            result = self.interp.default("masstorage start")

        self.assertTrue(result)
        do_masstorage.assert_called_once()
        self.assertIn("re-enumerates", self.interp.stdout.getvalue())

    def test_badusb_invalidates_session(self):
        with mock.patch.object(interpreter, "do_badusb") as do_badusb:
            result = self.interp.default("badusb --payload test.txt")

        self.assertTrue(result)
        do_badusb.assert_called_once()

    def test_scan_calls_handler_without_args(self):
        with mock.patch.object(interpreter, "do_scan") as do_scan:
            result = self.interp.default("scan")

        self.assertFalse(result)
        do_scan.assert_called_once_with()

    def test_module_use_set_run_dispatches(self):
        self.interp.default("use wifi/sniff")
        self.assertIn("wifi/sniff", self.interp.prompt)
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
        self.assertIn("wifi/sniff", self.interp.stdout.getvalue())

    def test_back_leaves_module(self):
        self.interp.default("use wifi/sniff")
        self.interp.default("back")
        self.assertNotIn("wifi/sniff", self.interp.prompt)


if __name__ == "__main__":
    unittest.main()
