import io
import unittest
from contextlib import redirect_stderr

from nrsuite_lib.cli import _extract_device_flag, build_parser


class ExtractDeviceFlagTests(unittest.TestCase):
    def test_device_before_subcommand(self):
        self.assertEqual(
            _extract_device_flag(["-d", "0", "scan"]),
            ("0", ["scan"]),
        )

    def test_device_after_subcommand(self):
        self.assertEqual(
            _extract_device_flag(["scan", "--device", "0"]),
            ("0", ["scan"]),
        )

    def test_device_equals_form(self):
        self.assertEqual(
            _extract_device_flag(["--device=/dev/ttyUSB0", "scan"]),
            ("/dev/ttyUSB0", ["scan"]),
        )

    def test_no_device_flag(self):
        self.assertEqual(
            _extract_device_flag(["scan", "--channel", "6"]),
            (None, ["scan", "--channel", "6"]),
        )

    def test_missing_device_value_is_an_error(self):
        with self.assertRaises(SystemExit):
            _extract_device_flag(["scan", "-d"])


class BuildParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_basic_commands(self):
        self.assertEqual(self.parser.parse_args(["devices"]).command, "devices")
        self.assertEqual(self.parser.parse_args(["scan"]).command, "scan")

    def test_sniff_defaults(self):
        args = self.parser.parse_args(["sniff"])
        self.assertEqual(args.command, "sniff")
        self.assertEqual(args.channel, 1)
        self.assertFalse(args.hop)
        self.assertEqual(args.interval, 300)
        self.assertFalse(args.eapol_only)
        self.assertEqual(args.client, "FF:FF:FF:FF:FF:FF")
        self.assertFalse(args.deauth)
        self.assertEqual(args.count, 0)
        self.assertEqual(args.duration, 0)
        self.assertIsNone(args.output)
        self.assertFalse(args.stream)

    def test_sniff_overrides(self):
        args = self.parser.parse_args([
            "sniff", "--channel", "11", "--hop", "--interval", "500",
            "--eapol-only", "--bssid", "AA:BB:CC:DD:EE:FF",
            "--client", "11:22:33:44:55:66", "--deauth",
            "--count", "10", "--duration", "30",
            "-o", "capture.pcap", "--stream",
        ])
        self.assertEqual(args.channel, 11)
        self.assertTrue(args.hop)
        self.assertEqual(args.interval, 500)
        self.assertTrue(args.eapol_only)
        self.assertEqual(args.bssid, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(args.client, "11:22:33:44:55:66")
        self.assertTrue(args.deauth)
        self.assertEqual(args.count, 10)
        self.assertEqual(args.duration, 30)
        self.assertEqual(args.output, "capture.pcap")
        self.assertTrue(args.stream)

    def test_deauth_requires_bssid_and_channel(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.parser.parse_args(["deauth"])
        args = self.parser.parse_args([
            "deauth", "--bssid", "AA:BB:CC:DD:EE:FF", "--channel", "6",
        ])
        self.assertEqual(args.command, "deauth")
        self.assertEqual(args.channel, 6)

    def test_beacon_defaults_and_options(self):
        args = self.parser.parse_args(["beacon"])
        self.assertEqual(args.beacon_action, "start")
        self.assertEqual(args.channel, 6)
        self.assertEqual(args.ssid, [])

        args = self.parser.parse_args([
            "beacon", "stop", "--ssid", "One", "--ssid", "Two",
            "--hidden", "--stable-bssid",
        ])
        self.assertEqual(args.beacon_action, "stop")
        self.assertEqual(args.ssid, ["One", "Two"])
        self.assertTrue(args.hidden)
        self.assertTrue(args.stable_bssid)

    def test_portal_options(self):
        args = self.parser.parse_args([
            "portal", "start", "--ssid", "MyAP", "--channel", "1",
            "--bssid", "AA:BB:CC:DD:EE:FF", "--file", "page.html",
        ])
        self.assertEqual(args.command, "portal")
        self.assertEqual(args.action, "start")
        self.assertEqual(args.ssid, "MyAP")
        self.assertEqual(args.channel, 1)
        self.assertEqual(args.bssid, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(args.file, "page.html")

    def test_ble_subcommands(self):
        badble = self.parser.parse_args([
            "ble", "badble", "--payload", "payload.txt",
            "--advertise", "Keyboard", "--pair-timeout", "30",
            "--run-delay", "1.5", "--keep-alive",
        ])
        self.assertEqual(badble.command, "ble")
        self.assertEqual(badble.ble_action, "badble")
        self.assertEqual(badble.payload, "payload.txt")
        self.assertEqual(badble.pair_timeout, 30)
        self.assertEqual(badble.run_delay, 1.5)
        self.assertTrue(badble.keep_alive)

        keyboard = self.parser.parse_args([
            "ble", "keyboard", "--advertise", "Keyboard2",
        ])
        self.assertEqual(keyboard.ble_action, "keyboard")
        self.assertEqual(keyboard.advertise, "Keyboard2")

    def test_masstorage_subcommands(self):
        start = self.parser.parse_args(["masstorage", "start"])
        self.assertEqual(start.msc_action, "start")
        files = self.parser.parse_args(["masstorage", "files"])
        self.assertEqual(files.msc_action, "files")
        free = self.parser.parse_args(["masstorage", "free"])
        self.assertEqual(free.msc_action, "free")
        delete = self.parser.parse_args(["masstorage", "delete", "capture.pcap"])
        self.assertEqual(delete.msc_action, "delete")
        self.assertEqual(delete.file, "capture.pcap")

    def test_badusb_options(self):
        args = self.parser.parse_args([
            "badusb", "--payload", "ducky.txt", "--masstorage",
        ])
        self.assertEqual(args.command, "badusb")
        self.assertEqual(args.payload, "ducky.txt")
        self.assertTrue(args.masstorage)


if __name__ == "__main__":
    unittest.main()
