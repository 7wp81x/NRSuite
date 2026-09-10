"""Console colors, logging, and small presentation helpers."""

import sys
import time

from . import config


class C:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    GREEN   = '\033[92m'
    BLUE    = '\033[94m'
    CYAN    = '\033[96m'
    YELLOW  = '\033[93m'
    RED     = '\033[91m'
    MAGENTA = '\033[95m'
    GRAY    = '\033[90m'


_LEVELS = {
    "info":  ("[*]", C.CYAN),
    "ok":    ("[+]", C.GREEN),
    "warn":  ("[!]", C.YELLOW),
    "err":   ("[x]", C.RED),
    "plain": ("", C.RESET),
}


def log(msg: str, color=None, level: str = "info"):
    tag, default_color = _LEVELS.get(level, _LEVELS["info"])
    color = color or default_color
    ts = time.strftime("%H:%M:%S")
    prefix = f"{tag}{C.RESET} " if tag else f"[{ts}] "
    entry = f"{prefix}{msg}"
    colored_entry = f"{color}{entry}{C.RESET}"

    if not config.IS_CHILD:
        print(colored_entry, file=sys.stderr, flush=True)

    with open(config.LOG_FILE, "a") as f:
        f.write(colored_entry + "\n")


def banner():
    logo = """
\033[1;92m _____ _____ \033[1;96m_____     _ _       
\033[1;92m|   | | __  |\033[1;96m   __|_ _|_| |_ ___ 
\033[1;92m| | | |    -|\033[1;96m__   | | | |  _| -_|
\033[1;92m|_|___|__|__|\033[1;96m_____|___|_|_| |___| v1.2

\033[1;92m[+]\033[0m Github \033[4;92m@7wp81x/NRSuite\033[0m
"""
    print(logo)


def _signal_bars(rssi: int) -> str:
    """Return a quick visual signal strength indicator."""
    if rssi >= -50:
        return "▂▄▆█"
    elif rssi >= -65:
        return "▂▄▆_"
    elif rssi >= -75:
        return "▂▄__"
    else:
        return "▂___"
