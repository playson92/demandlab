"""Snapshot or verify immutable research inputs and outputs without importing research."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path, canonical=False):
    data = path.read_bytes()
    if canonical and path.suffix not in {".parquet", ".png"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def protected_files():
    files = []
    for directory in ["data/demo", "reports", "sql", "configs", "src/demandlab"]:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                if directory == "src/demandlab" and path.name == "reporting.py":
                    continue
                files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "check"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--canonical", action="store_true")
    args = parser.parse_args()
    if args.action == "snapshot":
        record = {
            "base_sha": "68277b676027369b815f76baea20ff057fcfb470",
            "canonical_text": args.canonical,
            "files": {
                path.relative_to(ROOT).as_posix(): digest(path, args.canonical)
                for path in protected_files()
            },
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"Snapshot: {len(record['files'])} protected files")
    else:
        record = json.loads(args.manifest.read_text(encoding="utf-8"))
        changed = [
            name
            for name, expected in record["files"].items()
            if not (ROOT / name).is_file()
            or digest(ROOT / name, record["canonical_text"]) != expected
        ]
        print(
            json.dumps(
                {
                    "status": "FAIL" if changed else "PASS",
                    "files": len(record["files"]),
                    "changed": changed,
                }
            )
        )
        if changed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
