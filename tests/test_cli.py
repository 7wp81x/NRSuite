import unittest

from nrsuite_lib.cli import _extract_device_flag


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


if __name__ == "__main__":
    unittest.main()
