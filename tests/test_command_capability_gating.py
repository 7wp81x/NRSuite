import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from nrsuite_lib.commands import badusb, ble, storage


class FakeProto:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.calls = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def send_cmd(self, cmd, args=None, timeout=None):
        self.calls.append((cmd, args))
        return {"ok": True}


class FakeRx:
    def stop(self):
        pass

    def join(self, timeout=None):
        pass


class CommandCapabilityGatingTests(unittest.TestCase):
    def setUp(self):
        self.proto = FakeProto()
        self.rx = FakeRx()
        self.bridge = mock.patch
        self.payload = tempfile.NamedTemporaryFile("w", delete=False)
        self.payload.write("REM test\n")
        self.payload.close()

    def tearDown(self):
        os.unlink(self.payload.name)

    def test_ble_badble_stops_before_ble_start_without_bluetooth(self):
        args = SimpleNamespace(payload=self.payload.name, advertise="Test")
        with mock.patch.object(ble, "log"), \
             mock.patch.object(ble, "_setup_bridge", return_value=(None, self.rx, None, self.proto)), \
             mock.patch.object(ble, "_drain_stale"), \
             mock.patch.object(ble, "_wait_for_ready"), \
             mock.patch.object(ble, "ensure_bluetooth", return_value=False), \
             mock.patch.object(ble, "_stop_bridge") as stop_bridge:
            ble.do_ble_badble(args=args)

        stop_bridge.assert_called_once_with(self.proto, self.rx, timeout=2)
        self.assertNotIn("BLE_START", [cmd for cmd, _ in self.proto.calls])

    def test_mass_storage_start_stops_before_msc_without_otg(self):
        with mock.patch.object(storage, "log"), \
             mock.patch.object(storage, "_setup_bridge", return_value=(None, self.rx, None, self.proto)), \
             mock.patch.object(storage, "_drain_stale"), \
             mock.patch.object(storage, "_wait_for_ready"), \
             mock.patch.object(storage, "ensure_usb_otg", return_value=False), \
             mock.patch.object(storage, "_stop_bridge") as stop_bridge:
            storage.do_masstorage_start(args=None)

        stop_bridge.assert_called_once_with(self.proto, self.rx, timeout=3)
        self.assertNotIn("START_MSC", [cmd for cmd, _ in self.proto.calls])

    def test_badusb_stops_before_upload_without_otg(self):
        args = SimpleNamespace(payload=self.payload.name)
        with mock.patch.object(badusb, "log"), \
             mock.patch.object(badusb, "_setup_bridge", return_value=(None, self.rx, None, self.proto)), \
             mock.patch.object(badusb, "_drain_stale"), \
             mock.patch.object(badusb, "_wait_for_ready"), \
             mock.patch.object(badusb, "ensure_usb_otg", return_value=False), \
             mock.patch.object(badusb, "_stop_bridge") as stop_bridge:
            badusb.do_badusb(args=args)

        stop_bridge.assert_called_once_with(self.proto, self.rx, timeout=3)
        self.assertNotIn("SET_FILE_CHUNK", [cmd for cmd, _ in self.proto.calls])


if __name__ == "__main__":
    unittest.main()
