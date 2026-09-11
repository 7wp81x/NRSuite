import unittest

from nrsuite_lib.ui import _signal_bars


class SignalBarsTests(unittest.TestCase):
    def test_signal_bar_thresholds(self):
        self.assertEqual(_signal_bars(-40), "▂▄▆█")
        self.assertEqual(_signal_bars(-55), "▂▄▆_")
        self.assertEqual(_signal_bars(-70), "▂▄__")
        self.assertEqual(_signal_bars(-90), "▂___")


if __name__ == "__main__":
    unittest.main()
