import unittest

from nrsuite_lib.capabilities import ensure_bluetooth, ensure_usb_otg, get_chip


class FakeProto:
    def __init__(self, chip=None):
        self.chip = chip
        self.calls = []

    def send_cmd(self, cmd, timeout=None):
        self.calls.append((cmd, timeout))
        if self.chip is None:
            return None
        return {"ok": True, "chip": self.chip}


class CapabilityTests(unittest.TestCase):
    def test_esp32_c3_has_bluetooth_but_no_otg(self):
        proto = FakeProto("ESP32-C3")
        self.assertTrue(ensure_bluetooth(proto, log_func=lambda *a, **k: None))
        self.assertFalse(ensure_usb_otg(proto, "USB mass storage mode", log_func=lambda *a, **k: None))

    def test_esp32_s2_has_otg_but_no_bluetooth(self):
        proto = FakeProto("ESP32-S2")
        self.assertFalse(ensure_bluetooth(proto, log_func=lambda *a, **k: None))
        self.assertTrue(ensure_usb_otg(proto, "USB mass storage mode", log_func=lambda *a, **k: None))

    def test_esp32_s3_has_both(self):
        proto = FakeProto("ESP32-S3")
        self.assertTrue(ensure_bluetooth(proto, log_func=lambda *a, **k: None))
        self.assertTrue(ensure_usb_otg(proto, "BadUSB", log_func=lambda *a, **k: None))

    def test_classic_esp32_has_bluetooth_but_no_otg(self):
        proto = FakeProto("ESP32")
        self.assertTrue(ensure_bluetooth(proto, log_func=lambda *a, **k: None))
        self.assertFalse(ensure_usb_otg(proto, "BadUSB", log_func=lambda *a, **k: None))

    def test_chip_is_cached(self):
        proto = FakeProto("ESP32-C3")
        self.assertEqual(get_chip(proto), "ESP32-C3")
        self.assertEqual(get_chip(proto), "ESP32-C3")
        self.assertEqual(len(proto.calls), 1)

    def test_unknown_chip_warns_but_proceeds(self):
        proto = FakeProto("ESP32-C6")
        self.assertTrue(ensure_bluetooth(proto, log_func=lambda *a, **k: None))
        self.assertTrue(ensure_usb_otg(proto, "BadUSB", log_func=lambda *a, **k: None))

    def test_missing_status_response_does_not_block(self):
        proto = FakeProto(None)
        messages = []
        self.assertTrue(ensure_bluetooth(proto, log_func=lambda msg, *a, **k: messages.append(msg)))
        self.assertIn("could not determine", " ".join(messages).lower())

    def test_unsupported_feature_logs_warning(self):
        proto = FakeProto("ESP32-S2")
        messages = []
        self.assertFalse(
            ensure_bluetooth(proto, log_func=lambda msg, *a, **k: messages.append(msg))
        )
        self.assertTrue(any("no Bluetooth radio" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
