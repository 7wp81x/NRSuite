import unittest

from nrsuite_lib.modules import ModuleRegistry


class ModuleRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry()

    def test_expected_modules_exist(self):
        for name in (
            "wifi/scan", "wifi/sniff", "wifi/deauth", "wifi/beacon",
            "wifi/portal", "ble/badble", "ble/keyboard", "storage/start",
            "storage/files", "storage/delete", "storage/free", "usb/badusb",
        ):
            self.assertIn(name, self.registry.modules)

    def test_use_group_lists_modules(self):
        ok, message = self.registry.use("wifi")
        self.assertFalse(ok)
        self.assertIn("wifi/sniff", message)

    def test_sniff_options_build_argv(self):
        ok, _ = self.registry.use("wifi/sniff")
        self.assertTrue(ok)
        self.assertTrue(self.registry.set_value("channel", "6")[0])
        self.assertTrue(self.registry.set_value("hop", "true")[0])
        self.assertTrue(self.registry.set_value("bssid", "AA:BB:CC:DD:EE:FF")[0])

        argv = self.registry.build()
        args = self.registry.parse(argv)
        self.assertEqual(args.command, "sniff")
        self.assertEqual(args.channel, 6)
        self.assertTrue(args.hop)
        self.assertEqual(args.bssid, "AA:BB:CC:DD:EE:FF")

    def test_portal_options_build_argv(self):
        self.registry.use("wifi/portal")
        self.registry.set_value("action", "start")
        self.registry.set_value("ssid", "Test AP")
        self.registry.set_value("channel", "6")

        argv = self.registry.build()
        args = self.registry.parse(argv)
        self.assertEqual(args.action, "start")
        self.assertEqual(args.ssid, "Test AP")
        self.assertEqual(args.channel, 6)

    def test_beacon_append_option(self):
        self.registry.use("wifi/beacon")
        self.registry.set_value("action", "start")
        self.registry.set_value("ssid", "One")
        self.registry.set_value("ssid", "Two")

        args = self.registry.parse(self.registry.build())
        self.assertEqual(args.beacon_action, "start")
        self.assertEqual(args.ssid, ["One", "Two"])

    def test_storage_delete_option(self):
        self.registry.use("storage/delete")
        self.registry.set_value("file", "capture.pcap")
        args = self.registry.parse(self.registry.build())
        self.assertEqual(args.command, "masstorage")
        self.assertEqual(args.msc_action, "delete")
        self.assertEqual(args.file, "capture.pcap")

    def test_unknown_option_is_rejected(self):
        self.registry.use("wifi/sniff")
        ok, message = self.registry.set_value("nope", "1")
        self.assertFalse(ok)
        self.assertIn("Unknown option", message)


if __name__ == "__main__":
    unittest.main()
