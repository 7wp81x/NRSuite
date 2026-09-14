import os
import tempfile
import unittest

from nrsuite_lib.hooks import HookBus
from nrsuite_lib.modules import ModuleRegistry
from nrsuite_lib.plugins import PluginManager


PLUGIN_SOURCE = '''
def handler(context):
    context["plugin_ran"] = True
    return {"ok": True}

def on_post(event, payload):
    payload.setdefault("seen_events", []).append(event)

def register(api):
    api.register_module("my_tool", handler, "Test plugin module")
    api.on("post_module", on_post)
'''


POST_SOURCE = '''
def post(context):
    return {"ok": True}

def register(api):
    api.register_post("post/test", post, "Test post script")
'''


class PluginManagerTests(unittest.TestCase):
    def test_load_file_registers_module_and_hook(self):
        registry = ModuleRegistry()
        hooks = HookBus()
        manager = PluginManager(registry, hooks, log_func=lambda *a, **k: None)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my_plugin.py")
            with open(path, "w") as f:
                f.write(PLUGIN_SOURCE)
            self.assertEqual(manager.load_file(path), ["my_plugin"])

        self.assertIn("plug/my_tool", registry.modules)

        payload = {"seen_events": []}
        hooks.emit("post_module", **payload)
        self.assertEqual(payload["seen_events"], ["post_module"])

    def test_missing_register_function_is_rejected(self):
        registry = ModuleRegistry()
        hooks = HookBus()
        manager = PluginManager(registry, hooks, log_func=lambda *a, **k: None)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad_plugin.py")
            with open(path, "w") as f:
                f.write("x = 1\n")
            with self.assertRaises(RuntimeError):
                manager.load_file(path)

    def test_load_posts_registers_post_script(self):
        registry = ModuleRegistry()
        hooks = HookBus()
        manager = PluginManager(registry, hooks, log_func=lambda *a, **k: None)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my_post.py")
            with open(path, "w") as f:
                f.write(POST_SOURCE)
            self.assertEqual(manager.load_posts([path]), ["my_post"])

        self.assertIn("post/test", registry.post_scripts)
        self.assertEqual(registry.post_scripts["post/test"]["source"], "my_post")
        self.assertEqual(len(manager.loaded_posts), 1)


if __name__ == "__main__":
    unittest.main()
