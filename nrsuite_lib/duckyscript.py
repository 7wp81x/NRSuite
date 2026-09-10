"""Pure DuckyScript helpers used by BLE HID and BadUSB flows.

These helpers have no dependency on espbridge, USB, or the CLI globals.
"""

SCRIPT_COMMANDS = {"STRING", "STRINGLN", "DELAY", "REM"}

KEY_NAMES = {
    "CTRL", "CONTROL", "LCTRL", "RCTRL",
    "ALT", "LALT", "RALT",
    "SHIFT", "LSHIFT", "RSHIFT",
    "GUI", "WINDOWS", "COMMAND", "LGUI", "RGUI",
    "ENTER", "RETURN", "TAB", "ESC", "ESCAPE", "BACKSPACE", "BACK",
    "DELETE", "DEL", "SPACE", "UP", "DOWN", "LEFT", "RIGHT",
    "HOME", "END", "INSERT", "PAGEUP", "PGUP", "PAGEDOWN", "PGDN",
    "PRINTSCREEN", "PRTSC",
}


def split_pipe_commands(raw: str):
    """
    Split a raw input line into individual script commands using '|' as
    the delimiter, with escaping:

      |    -> command separator
      ||   -> literal "|" character (no separator)
      |||  -> literal "|" character followed by a newline, still no separator

    Example:
      "DELAY 3000|STRINGLN test|STRING HELLO WORLD|"
        -> ["DELAY 3000", "STRINGLN test", "STRING HELLO WORLD", ""]
      "STRING a||b"
        -> ["STRING a|b"]
      "STRING a|||b"
        -> ["STRING a|\nb"]
    """
    PLACEHOLDER_LITERAL = "\x00PIPE_LITERAL\x00"
    PLACEHOLDER_LITERAL_NL = "\x00PIPE_LITERAL_NL\x00"

    # Longest match first so ||| isn't mis-split into || + |
    tmp = raw.replace("|||", PLACEHOLDER_LITERAL_NL)
    tmp = tmp.replace("||", PLACEHOLDER_LITERAL)

    parts = tmp.split("|")

    result = []
    for part in parts:
        part = part.replace(PLACEHOLDER_LITERAL_NL, "|\n")
        part = part.replace(PLACEHOLDER_LITERAL, "|")
        result.append(part)

    return result


def looks_like_script_line(line: str) -> bool:
    """Return True when a keyboard input line should be sent as raw script."""
    first = line.split(" ", 1)[0].upper()
    if first in SCRIPT_COMMANDS:
        return True
    if first in KEY_NAMES:
        return True
    if first.startswith("F") and first[1:].isdigit():
        n = int(first[1:])
        if 1 <= n <= 12:
            return True
    return False
