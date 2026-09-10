"""Pure EAPOL/4-way-handshake parsing helpers.

This module deliberately has no dependency on espbridge or the NRSuite CLI
globals so it can be unit-tested on a normal host.
"""

import struct


def parse_eapol_message(payload: bytes, handshake_state, log_func=None):
    """
    Dynamically strip variable-length Radiotap headers and detect EAPOL
    messages in an 802.11 data frame.

    ``handshake_state`` is mutated in place with M1..M4 booleans. The same
    dict is returned for convenience.
    """
    _log = log_func or (lambda *args, **kwargs: None)

    try:
        if len(payload) < 4:
            return handshake_state

        # Skip Radiotap
        rt_len = struct.unpack("<H", payload[2:4])[0]
        if len(payload) < rt_len + 34:
            return handshake_state

        mac_base = rt_len
        fc0 = payload[mac_base]
        type_val = (fc0 & 0x0C) >> 2

        if type_val != 2:  # Data frames only for EAPOL
            return handshake_state

        # Dynamic header length
        to_ds = (payload[mac_base + 1] & 0x01) != 0
        from_ds = (payload[mac_base + 1] & 0x02) != 0
        hdr_len = 24
        if to_ds and from_ds:
            hdr_len = 30
        subtype = (fc0 >> 4) & 0x0F
        if subtype in [8, 9, 10, 11]:  # QoS Data
            hdr_len += 2

        llc_base = mac_base + hdr_len
        search_window = payload[llc_base:llc_base + 20]

        if b'\x88\x8E' in search_window:
            eth_idx = llc_base + search_window.index(b'\x88\x8E')
            eapol_start = eth_idx + 2

            if len(payload) < eapol_start + 8:
                return handshake_state

            packet_type = payload[eapol_start + 1]
            if packet_type in [1, 3]:
                key_info = payload[eapol_start + 5:eapol_start + 7]
                k_flags = (key_info[0] << 8) | key_info[1]

                is_pairwise = bool(k_flags & (1 << 3))
                is_ack      = bool(k_flags & (1 << 7))
                is_mic      = bool(k_flags & (1 << 8))
                is_secure   = bool(k_flags & (1 << 9))
                is_error    = bool(k_flags & (1 << 10))

                if is_pairwise and not is_error:
                    if is_ack and not is_mic:
                        if not handshake_state["M1"]:
                            handshake_state["M1"] = True
                            _log("[EAPOL OK] M1 Captured!", level="ok")
                    elif not is_ack and is_mic and not is_secure:
                        if handshake_state["M1"] and not handshake_state["M2"]:
                            handshake_state["M2"] = True
                            _log("[EAPOL OK] M2 Captured!", level="ok")
                    elif is_ack and is_mic and is_secure:
                        if handshake_state["M2"] and not handshake_state["M3"]:
                            handshake_state["M3"] = True
                            _log("[EAPOL OK] M3 Captured!", level="ok")
                    elif not is_ack and is_mic and is_secure:
                        if handshake_state["M3"] and not handshake_state["M4"]:
                            handshake_state["M4"] = True
                            _log("[EAPOL OK] M4 Captured!", level="ok")

    except Exception:
        pass

    return handshake_state
