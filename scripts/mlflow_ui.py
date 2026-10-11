"""Start a loopback-only MLflow UI using the pipeline's local SQLite store."""

import argparse
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=5000)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
store = root / "output/mlflow"
store.mkdir(parents=True, exist_ok=True)
raise SystemExit(
    subprocess.call(
        [
            sys.executable,
            "-m",
            "mlflow",
            "ui",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--workers",
            "1",
            "--backend-store-uri",
            "sqlite:///" + (store / "tracking.sqlite").as_posix(),
            "--default-artifact-root",
            (store / "artifacts").as_uri(),
        ]
    )
)
