"""Paths, protocol constants, and runtime storage initialization for NRSuite."""

import os


# Repo root: one directory above this package.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_FILE = os.path.join(DATA_DIR, "wifi_tool.log")
ENTRYPOINT = os.path.join(BASE_DIR, "nrsuite")

IS_CHILD = "TERMUX_USB_FD" in os.environ

PROTO_MAX_CHUNK = 1024
JSON_OVERHEAD_ESTIMATE = 100
MAX_B64_LEN = PROTO_MAX_CHUNK - JSON_OVERHEAD_ESTIMATE
HTML_CHUNK_SIZE = 512


def init_storage() -> None:
    """Create the local data directory and reset the parent log file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not IS_CHILD:
        with open(LOG_FILE, "w") as f:
            f.write("")
