import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from nrsuite_lib import devices


class ResolveDeviceTests(unittest.TestCase):
    def test_numeric_index(self):
        with mock.patch.object(
            devices, "_enumerate_usb_paths", return_value=["/dev/a", "/dev/b"]
        ):
            self.assertEqual(devices.resolve_device("0"), "/dev/a")
            self.assertEqual(devices.resolve_device("1"), "/dev/b")

    def test_one_device_is_auto_selected(self):
        with mock.patch.object(
            devices, "_enumerate_usb_paths", return_value=["/dev/only"]
        ):
            self.assertEqual(devices.resolve_device(None), "/dev/only")

    def test_multiple_devices_use_auto_detect(self):
        with mock.patch.object(
            devices, "_enumerate_usb_paths", return_value=["/dev/a", "/dev/b"]
        ), mock.patch.object(devices, "auto_detect_device", return_value="/dev/chosen"):
            self.assertEqual(devices.resolve_device(None), "/dev/chosen")

    def test_explicit_dev_path_is_trusted(self):
        with mock.patch.object(devices, "_enumerate_usb_paths", return_value=[]):
            self.assertEqual(devices.resolve_device("/dev/custom"), "/dev/custom")

    def test_exact_and_unique_substring_match(self):
        with mock.patch.object(
            devices,
            "_enumerate_usb_paths",
            return_value=["/dev/ttyUSB0", "/dev/ttyACM0"],
        ):
            self.assertEqual(devices.resolve_device("/dev/ttyUSB0"), "/dev/ttyUSB0")
            self.assertEqual(devices.resolve_device("ACM"), "/dev/ttyACM0")

    def test_ambiguous_substring_raises(self):
        with mock.patch.object(
            devices, "_enumerate_usb_paths", return_value=["/dev/a", "/dev/ab"]
        ):
            with self.assertRaises(RuntimeError):
                devices.resolve_device("a")

    def test_missing_device_raises(self):
        with mock.patch.object(
            devices, "_enumerate_usb_paths", return_value=["/dev/a"]
        ):
            with self.assertRaises(RuntimeError):
                devices.resolve_device("missing")


class BootstrapInteractiveTests(unittest.TestCase):
    def test_interactive_bootstrap_uses_tty_open_path(self):
        with mock.patch.object(devices, "resolve_device", return_value="/dev/test"), \
             mock.patch.object(devices, "request_permission", return_value=True), \
             mock.patch.object(devices, "open_usb_device") as open_usb_device, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            devices.bootstrap("interact", [], interactive=True)

        open_usb_device.assert_called_once()
        args, kwargs = open_usb_device.call_args
        self.assertEqual(args[0], "/dev/test")
        self.assertIn("interact", args[1])
        self.assertTrue(kwargs["export_as_env"])


if __name__ == "__main__":
    unittest.main()
