import unittest

from nrsuite_lib.session import NRSuiteSession, _ProtoProxy, _RxProxy


class FakeProtocol:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.reset_calls = 0
        self.on_event = "old-event"
        self.on_pcap = "old-pcap"

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def reset(self):
        self.reset_calls += 1

    def send_cmd(self, cmd, args=None, timeout=None):
        return {"ok": True, "cmd": cmd, "args": args, "timeout": timeout}


class FakeRx:
    def __init__(self):
        self.stopped = 0
        self.joined = False

    def stop(self):
        self.stopped += 1

    def join(self, timeout=None):
        self.joined = True

    def readline(self, timeout=None):
        return b"data"


class RxProxyTests(unittest.TestCase):
    def test_stop_and_join_are_noops_but_reads_delegate(self):
        rx = FakeRx()
        proxy = _RxProxy(rx)
        proxy.stop()
        proxy.join(timeout=1)
        self.assertEqual(rx.stopped, 0)
        self.assertFalse(rx.joined)
        self.assertEqual(proxy.readline(timeout=0.1), b"data")


class ProtoProxyTests(unittest.TestCase):
    def test_start_and_stop_are_noops_but_operations_delegate(self):
        proto = FakeProtocol()
        proxy = _ProtoProxy(proto)
        proxy.start()
        proxy.stop()
        self.assertEqual(proto.started, 0)
        self.assertEqual(proto.stopped, 0)

        proxy.on_event = "new-event"
        self.assertEqual(proto.on_event, "new-event")
        self.assertEqual(proxy.send_cmd("PING", timeout=1)["cmd"], "PING")


class SessionTests(unittest.TestCase):
    def test_proxy_bundle_wraps_shared_bridge(self):
        session = NRSuiteSession()
        session.device = object()
        session.tx = object()
        session.rx = FakeRx()
        session.proto = FakeProtocol()

        device, rx, tx, proto = session.proxy_bundle()
        self.assertIs(device, session.device)
        self.assertIs(tx, session.tx)
        self.assertIsInstance(rx, _RxProxy)
        self.assertIsInstance(proto, _ProtoProxy)

    def test_begin_and_end_command_clear_callbacks_and_parser(self):
        session = NRSuiteSession()
        session.proto = FakeProtocol()

        session.begin_command()
        self.assertIsNone(session.proto.on_event)
        self.assertIsNone(session.proto.on_pcap)
        self.assertEqual(session.proto.reset_calls, 1)

        session.end_command()
        self.assertEqual(session.proto.reset_calls, 2)


if __name__ == "__main__":
    unittest.main()
