import unittest

from nrsuite_lib.hooks import HookBus


class HookBusTests(unittest.TestCase):
    def test_emit_calls_registered_hooks(self):
        hooks = HookBus()
        seen = []
        hooks.on("post_module", lambda event, payload: seen.append((event, payload["name"])))
        hooks.emit("post_module", name="wifi/scan")
        self.assertEqual(seen, [("post_module", "wifi/scan")])

    def test_off_removes_hook(self):
        hooks = HookBus()
        seen = []
        callback = lambda event, payload: seen.append(event)
        hooks.on("event", callback)
        hooks.off("event", callback)
        hooks.emit("event", value=1)
        self.assertEqual(seen, [])

    def test_hook_errors_are_reported(self):
        errors = []
        hooks = HookBus(on_error=lambda event, exc: errors.append((event, str(exc))))
        hooks.on("bad", lambda event, payload: 1 / 0)
        hooks.emit("bad")
        self.assertEqual(errors[0][0], "bad")
        self.assertIn("division by zero", errors[0][1])


if __name__ == "__main__":
    unittest.main()
