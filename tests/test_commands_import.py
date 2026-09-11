import unittest

from nrsuite_lib import commands


class CommandImportTests(unittest.TestCase):
    def test_all_commands_are_callable(self):
        self.assertTrue(commands.__all__)
        for name in commands.__all__:
            self.assertTrue(callable(getattr(commands, name)), name)


if __name__ == "__main__":
    unittest.main()
