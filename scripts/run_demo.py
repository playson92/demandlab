"""Launch the bundled offline demo from any directory, without Git or uv."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--address", default="127.0.0.1")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = Path(__file__).resolve().parents[1]
    local_python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Use the project's interpreter even when the launcher was called by system Python.
    python = str(local_python) if local_python.is_file() else sys.executable
    command = [
        python,
        "-m",
        "streamlit",
        "run",
        str(root / "app" / "streamlit_app.py"),
        "--server.address",
        args.address,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    try:
        return subprocess.call(command, cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
