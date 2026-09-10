import unittest

from nrsuite_lib.duckyscript import looks_like_script_line, split_pipe_commands


class SplitPipeCommandsTests(unittest.TestCase):
    def test_splits_plain_pipe_commands(self):
        self.assertEqual(
            split_pipe_commands("DELAY 3000|STRINGLN test|STRING HELLO WORLD|"),
            ["DELAY 3000", "STRINGLN test", "STRING HELLO WORLD", ""],
        )

    def test_double_pipe_is_literal_pipe(self):
        self.assertEqual(
            split_pipe_commands("STRING a||b"),
            ["STRING a|b"],
        )

    def test_triple_pipe_is_literal_pipe_plus_newline(self):
        self.assertEqual(
            split_pipe_commands("STRING a|||b"),
            ["STRING a|\nb"],
        )


class LooksLikeScriptLineTests(unittest.TestCase):
    def test_script_commands(self):
        for line in ("STRING hello", "STRINGLN hello", "DELAY 500", "REM comment"):
            self.assertTrue(looks_like_script_line(line))

    def test_key_combo(self):
        self.assertTrue(looks_like_script_line("CTRL ALT DEL"))
        self.assertTrue(looks_like_script_line("GUI r"))

    def test_function_keys(self):
        self.assertTrue(looks_like_script_line("F1"))
        self.assertTrue(looks_like_script_line("F12"))
        self.assertFalse(looks_like_script_line("F13"))

    def test_plain_text_is_not_script(self):
        self.assertFalse(looks_like_script_line("hello world"))


if __name__ == "__main__":
    unittest.main()
