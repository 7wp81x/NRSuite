import os
import struct
import tempfile
import unittest

from nrsuite_lib.modules import ModuleRegistry
from nrsuite_lib.post_scripts import count_pcap_packets, post_count_packet, register_builtin


def _write_test_pcap(path, records=2):
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i in range(records):
            payload = b"x" * 4
            f.write(struct.pack("<IIII", 1, i, len(payload), len(payload)))
            f.write(payload)


class PostScriptTests(unittest.TestCase):
    def test_count_pcap_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.pcap")
            _write_test_pcap(path, records=3)
            self.assertEqual(count_pcap_packets(path), 3)

    def test_post_count_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.pcap")
            _write_test_pcap(path, records=2)
            result = post_count_packet({"files": [path]})
            self.assertTrue(result["ok"])
            self.assertEqual(result["packets"], 2)

    def test_post_count_packet_without_file(self):
        result = post_count_packet({"files": []})
        self.assertFalse(result["ok"])

    def test_register_builtin(self):
        registry = ModuleRegistry()
        register_builtin(registry)
        self.assertIn("post/wifi/count_packet", registry.post_scripts)


if __name__ == "__main__":
    unittest.main()
