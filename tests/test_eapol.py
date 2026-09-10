import struct
import unittest

from nrsuite_lib.eapol import parse_eapol_message


def _new_handshake_state():
    return {"M1": False, "M2": False, "M3": False, "M4": False}


def _data_frame(key_info: bytes, packet_type: int = 3) -> bytes:
    """Build a minimal Radiotap + 802.11 data + LLC/SNAP EAPOL frame."""
    radiotap_len = 8
    # Radiotap length lives at bytes 2..3.
    radiotap = b"\x00\x00" + struct.pack("<H", radiotap_len) + b"\x00" * (radiotap_len - 4)

    # 24-byte 802.11 data header: FC=0x08 -> data frame, no ToDS/FromDS.
    mac_header = bytearray(24)
    mac_header[0] = 0x08

    # LLC/SNAP header ending in the EtherType used by EAPOL (0x888E).
    llc_snap = b"\xaa\xaa\x03\x00\x00\x00\x88\x8e"

    # EAPOL: version, type, 2-byte length, descriptor type, then key-info.
    eapol = bytes([1, packet_type, 0, 0, 0]) + key_info + b"\x00"

    return radiotap + bytes(mac_header) + llc_snap + eapol


class EapolParserTests(unittest.TestCase):
    def test_m1_through_m4_are_detected_in_order(self):
        state = _new_handshake_state()
        log_messages = []

        def log(msg, color=None, level="info"):
            log_messages.append(msg)

        parse_eapol_message(_data_frame(b"\x00\x88"), state, log)  # M1: ack, no MIC
        self.assertTrue(state["M1"])
        self.assertFalse(any(state[k] for k in ("M2", "M3", "M4")))

        parse_eapol_message(_data_frame(b"\x01\x08"), state, log)  # M2: MIC, not secure
        self.assertTrue(state["M2"])

        parse_eapol_message(_data_frame(b"\x03\x88"), state, log)  # M3: ack + MIC + secure
        self.assertTrue(state["M3"])

        parse_eapol_message(_data_frame(b"\x03\x08"), state, log)  # M4: MIC + secure, no ack
        self.assertTrue(state["M4"])

        self.assertEqual(
            [m for m in log_messages if m.startswith("[EAPOL OK]")],
            [
                "[EAPOL OK] M1 Captured!",
                "[EAPOL OK] M2 Captured!",
                "[EAPOL OK] M3 Captured!",
                "[EAPOL OK] M4 Captured!",
            ],
        )

    def test_m2_before_m1_is_ignored(self):
        state = _new_handshake_state()
        parse_eapol_message(_data_frame(b"\x01\x08"), state)
        self.assertFalse(state["M2"])

    def test_non_data_frame_is_ignored(self):
        state = _new_handshake_state()
        frame = bytearray(_data_frame(b"\x00\x88"))
        frame[8] = 0x80  # management frame, not data
        parse_eapol_message(bytes(frame), state)
        self.assertFalse(any(state.values()))

    def test_short_frame_is_ignored(self):
        state = _new_handshake_state()
        parse_eapol_message(b"\x00\x00", state)
        self.assertFalse(any(state.values()))


if __name__ == "__main__":
    unittest.main()
