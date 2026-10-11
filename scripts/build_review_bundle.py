"""Package committed delivery bytes and explicitly identified runtime evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import platform
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

RUNTIME_EVIDENCE = (
    "output/frontend/junit.xml",
    "output/frontend/pytest-final.log",
    "output/frontend/ui-final.log",
    "output/frontend/pytest-console.log",
    "output/frontend/bootstrap-zip.log",
    "output/frontend/code_changes.diff",
    "output/frontend/docker-build.log",
    "output/frontend/clean-demo.json",
    "output/frontend/protected_before.json",
    "output/frontend/protected_after.json",
    "output/frontend/review.md",
    "output/frontend/browser-final/browser_checks.json",
    "output/frontend/browser-final/inventory_visible.json",
    "output/frontend/browser-final/inventory_visible.csv",
    "output/frontend/docker-browser/browser_checks.json",
    "output/frontend/zip-browser/browser_checks.json",
    "output/frontend/clone-browser/browser_checks.json",
) + tuple(
    "output/frontend/browser-final/" + name
    for name in (
        "frontend_product_1440.png",
        "frontend_inventory_1440.png",
        "frontend_methods_1440.png",
        "frontend_product_390.png",
        "frontend_inventory_390.png",
        "frontend_methods_390.png",
        "frontend_zoom_200.png",
    )
)
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".cache",
    "cache",
    "mlruns",
    "node_modules",
    "output",
}
EXCLUDED_SUFFIXES = {
    ".xlsx",
    ".xls",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".duckdb",
    ".wal",
    ".pyc",
    ".pyo",
    ".pkl",
    ".pickle",
    ".joblib",
    ".onnx",
    ".pt",
    ".pth",
}
PACKAGES = (
    "demandlab",
    "duckdb",
    "pandas",
    "numpy",
    "scikit-learn",
    "mlflow",
    "streamlit",
    "plotly",
    "pyarrow",
    "openpyxl",
    "pytest",
    "ruff",
)


def git(root: Path, *arguments: str, allow_missing: bool = False) -> bytes:
    """Run Git without a shell, retaining exact committed file bytes."""
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        if allow_missing:
            return b""
        raise RuntimeError(
            f"Git {' '.join(arguments)} failed: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout


def require_clean(root: Path) -> None:
    changes = git(root, "status", "--porcelain", "--untracked-files=no").decode("utf-8")
    if changes.strip():
        raise RuntimeError(
            "Commit all tracked changes before generating the delivery bundle:\n" + changes
        )


def permitted(path: str) -> bool:
    """Keep public demo data, excluding local sources, environments and models."""
    parts = PurePosixPath(path).parts
    if any(part.lower() in EXCLUDED_DIRECTORIES for part in parts):
        return False
    if len(parts) > 1 and parts[0] == "data" and parts[1] in {"raw", "interim", "processed"}:
        return False
    if any(part.lower() in {"models", "secrets"} for part in parts):
        return False
    if PurePosixPath(path).suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return False
    return True


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def read_json(files: dict[str, bytes], path: str) -> dict:
    data = files.get("project/" + path)
    return json.loads(data.decode("utf-8-sig")) if data is not None else {}


def overlay_checks(committed: dict, runtime: dict) -> dict:
    """Prefer post-commit evidence while retaining separately recorded earlier checks."""
    combined = dict(committed)
    for key, value in runtime.items():
        if isinstance(value, dict) and isinstance(combined.get(key), dict):
            combined[key] = overlay_checks(combined[key], value)
        else:
            combined[key] = value
    return combined


def package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {"python": platform.python_version()}
    for name in PACKAGES:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def repository_url(origin: str | None) -> str | None:
    if not origin:
        return None
    if origin.startswith("git@github.com:"):
        return "https://github.com/" + origin.split(":", 1)[1].removesuffix(".git")
    if origin.startswith("https://github.com/"):
        return origin.removesuffix(".git")
    return None


def metric_table(files: dict[str, bytes]) -> str:
    data = files.get("project/reports/metrics.csv")
    if data is None:
        return "Metrics artifact absent from the delivery commit; result table NOT_RUN."
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    columns = ["split", "method", "mae", "wape", "coverage80", "width80", "coverage95", "width95"]
    table = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column, "")
            if value.lower() in {"", "nan", "none", "null"}:
                value = "N/A"
            else:
                try:
                    value = f"{float(value):.3f}"
                except ValueError:
                    pass
            cells.append(value.replace("|", "\\|"))
        table.append("| " + " | ".join(cells) + " |")
    return "\n".join(table)


def build_bundle(root: Path) -> tuple[Path, float]:
    root = root.resolve()
    require_clean(root)
    delivery_sha = git(root, "rev-parse", "HEAD").decode().strip()
    branch = git(root, "branch", "--show-current").decode().strip()
    origin = git(root, "remote", "get-url", "origin", allow_missing=True).decode().strip() or None
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    files: dict[str, bytes] = {}
    provenance: dict[str, str] = {}
    excluded = []
    tracked = git(root, "ls-files", "-z").decode("utf-8").split("\0")
    for relative in sorted(path for path in tracked if path):
        if not permitted(relative):
            excluded.append(relative)
            continue
        archive_path = "project/" + relative
        files[archive_path] = git(root, "show", f"{delivery_sha}:{relative}")
        provenance[archive_path] = "exact_committed_bytes"
    runtime_records = []
    for relative in RUNTIME_EVIDENCE:
        local = root / relative
        if local.is_file():
            resolved = local.resolve()
            if not resolved.is_relative_to(root):
                raise RuntimeError(f"Runtime evidence escapes the project directory: {relative}")
            archive_path = "project/" + relative
            files[archive_path] = local.read_bytes()
            provenance[archive_path] = "local_runtime_evidence_not_part_of_delivery_commit"
            runtime_records.append(
                {
                    "path": archive_path,
                    "modified_at_utc": datetime.fromtimestamp(
                        local.stat().st_mtime, UTC
                    ).isoformat(),
                }
            )
    committed_checks = read_json(files, "reports/delivery_checks.json")
    runtime_checks = {}
    runtime_checks_path = root / "output" / "delivery_checks.json"
    if runtime_checks_path.is_file():
        if not runtime_checks_path.resolve().is_relative_to(root):
            raise RuntimeError("Runtime delivery checks escape the project directory")
        runtime_checks_bytes = runtime_checks_path.read_bytes()
        runtime_checks = json.loads(runtime_checks_bytes.decode("utf-8-sig"))
        if not isinstance(runtime_checks, dict):
            raise ValueError("Runtime delivery_checks.json must be a JSON object")
        runtime_sha = runtime_checks.get("delivery_sha")
        if runtime_sha is not None and runtime_sha != delivery_sha:
            raise ValueError(
                f"Runtime delivery checks refer to {runtime_sha}, but delivery commit is {delivery_sha}"
            )
        evidence_path = "evidence/delivery_checks.json"
        files[evidence_path] = runtime_checks_bytes
        provenance[evidence_path] = "post_commit_runtime_delivery_checks"
        runtime_records.append(
            {
                "path": evidence_path,
                "modified_at_utc": datetime.fromtimestamp(
                    runtime_checks_path.stat().st_mtime, UTC
                ).isoformat(),
            }
        )
    checks = overlay_checks(committed_checks, runtime_checks)
    frozen = read_json(files, "reports/freeze_manifest.json")
    selection = read_json(files, "reports/model_selection.json")
    source = read_json(files, "reports/data_manifest.json")
    repo_url = repository_url(origin)
    manifest = {
        "schema_version": 1,
        "created_at_utc": now.isoformat(),
        "delivery_sha": delivery_sha,
        "origin": origin,
        "branch": branch,
        "repository_url": repo_url,
        "branch_url": f"{repo_url}/tree/{branch}" if repo_url and branch else None,
        "commit_url": f"{repo_url}/commit/{delivery_sha}" if repo_url else None,
        "source_sha": frozen.get("original_forecasting_code", frozen.get("code", {})).get(
            "source_sha"
        ),
        "validation_source_sha": selection.get("code", {}).get("source_sha"),
        "training_working_tree_sha256": frozen.get(
            "original_forecasting_code", frozen.get("code", {})
        ).get("working_tree_sha256"),
        "validation_working_tree_sha256": selection.get("code", {}).get("working_tree_sha256"),
        "source_sha256": source.get("source_sha256"),
        "freeze_manifest_sha256": hashlib.sha256(
            files["project/reports/freeze_manifest.json"]
        ).hexdigest()
        if "project/reports/freeze_manifest.json" in files
        else None,
        "versions_at_bundle_creation": package_versions(),
        "versions_at_freeze": frozen.get("versions", {}),
        "delivery_checks": checks,
        "delivery_checks_committed": committed_checks,
        "delivery_checks_post_commit": runtime_checks,
        "delivery_checks_present": bool(checks),
        "status_policy": "Statuses are recorded evidence: post-commit runtime delivery checks override committed checks; absent checks are NOT_RUN, never inferred PASS.",
        "evidence": runtime_records,
        "excluded_tracked_paths": excluded,
        "inventory_excludes": ["inventory.json (self-reference would be circular)"],
        "source_policy": "All project files are exact delivery commit bytes, except explicitly listed local runtime evidence.",
    }
    files["manifest.json"] = json_bytes(manifest)
    provenance["manifest.json"] = "generated_delivery_metadata"
    state_present = "project/PROJECT_STATE.md" in files
    readme = f"""# DemandLab review bundle

Delivery commit: `{delivery_sha}`. Branch: `{branch or "detached HEAD"}`.
Created at {now.isoformat()}.

Repository: {repo_url or "Origin unavailable; see manifest.json"}

This package contains exact committed source, tests, documentation, public demo
artifacts and screenshots. Explicitly listed runtime logs/JUnit are local execution
evidence. The original XLSX, invoices, customer IDs, environments, caches, databases
and large models are excluded. The current delivery SHA is distinct from the code
used for validation and the frozen test; their identities are in manifest.json.

## Results and execution status

Frozen default method: `{selection.get("winner", "not recorded")}`.
Source range: {source.get("date_min", "not recorded")} to {source.get("date_max", "not recorded")}.
Last admitted date: {source.get("D", "not recorded")}.

{metric_table(files)}

MAE and widths are recorded units; WAPE is percent; coverage is a fraction.
N/A means unavailable or undefined. Validation and final test are separate stages.
The default was selected on validation, before calibration and final test.

Recorded delivery checks (post-commit evidence overrides committed checks; no inferred statuses):

```json
{json.dumps(checks if checks else {"status": "NOT_RUN", "reason": "No committed delivery_checks.json"}, indent=2, ensure_ascii=False)}
```

See [execution state](project/PROJECT_STATE.md){"" if state_present else " (absent from delivery commit)"},
[full README](project/README.md), [results](project/docs/results.md),
[methodology](project/docs/methodology.md),
[reproduction](project/docs/reproducibility.md), and
[committed delivery checks](project/reports/delivery_checks.json).
Optional authoritative post-commit CI evidence is stored separately in
`evidence/delivery_checks.json`, when provided. Its delivery SHA must match this
bundle's commit if the runtime evidence declares a delivery SHA.
Repository, pull request and CI links are preserved in the delivery checks above.

## Run the committed demo

Extract this ZIP and open PowerShell in its `project` directory:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\\run_app.ps1
# Full public-source reproduction; requires network or a local original workbook:
powershell -ExecutionPolicy Bypass -File scripts\\reproduce.ps1
# powershell -ExecutionPolicy Bypass -File scripts\\reproduce.ps1 -SourceFile C:\\data\\online_retail_II.xlsx
```

The demo uses bundled real aggregates and predictions without downloading UCI or
training on widget changes. Dependency installation still requires package access.

## Limits

Data ends in 2011 and describes recorded sales, not uncensored demand. Source
completeness is assumed when filling internal calendar gaps. Empirical interval
levels do not guarantee per-product coverage. Inventory is a hypothetical finite
28-day policy with explicit user-supplied costs, no actual historical stock data,
no demand backorders, and no ROI or replenishment optimality claim.

`inventory.json` records SHA-256 and size for every other included file. The
inventory excludes itself to avoid a circular hash. `manifest.json` records bundle
provenance, runtime evidence and installed versions. Code is MIT; derived UCI data
is CC BY 4.0 with attribution in [DATA_LICENSE](project/DATA_LICENSE.md).
"""
    files["README_REVIEW.md"] = readme.encode("utf-8")
    provenance["README_REVIEW.md"] = "generated_delivery_summary"
    inventory = {
        "schema_version": 1,
        "delivery_sha": delivery_sha,
        "self_excluded": "inventory.json",
        "files": [
            {
                "path": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "provenance": provenance[name],
            }
            for name, data in sorted(files.items())
        ],
    }
    files["inventory.json"] = json_bytes(inventory)
    destination = root / "output" / "codex_runs" / timestamp
    destination.mkdir(parents=True, exist_ok=False)
    bundle = destination / "REVIEW_BUNDLE.zip"
    temporary = destination / "REVIEW_BUNDLE.zip.part"
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
        with zipfile.ZipFile(temporary) as archive:
            corrupted = archive.testzip()
            if corrupted:
                raise RuntimeError(f"Corrupt ZIP member: {corrupted}")
            for entry in inventory["files"]:
                if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f"ZIP inventory mismatch: {entry['path']}")
        require_clean(root)
        if git(root, "rev-parse", "HEAD").decode().strip() != delivery_sha:
            raise RuntimeError("HEAD changed while preparing the bundle")
        temporary.replace(bundle)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return bundle.resolve(), bundle.stat().st_size / (1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    try:
        bundle, size_mb = build_bundle(arguments.root)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Bundle generation failed: {error}", file=sys.stderr)
        return 1
    print(str(bundle))
    print(f"Size: {size_mb:.2f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
