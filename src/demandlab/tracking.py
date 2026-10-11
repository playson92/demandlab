"""Local SQLite experiment tracking and code provenance."""

import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

import mlflow


def code_identity(root: Path) -> dict:
    """Record HEAD and content hash; HEAD alone cannot identify a dirty checkout."""

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, encoding="utf-8"
        ).strip()

    if not (root / ".git").exists():
        root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    names = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    for name in sorted(names):
        path = root / name
        if path.is_file() and (
            name.startswith(("src/", "app/", "sql/", "configs/"))
            or name in {"pyproject.toml", "uv.lock"}
        ):
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return {
        "source_sha": git("rev-parse", "HEAD"),
        "working_tree_sha256": digest.hexdigest(),
        "dirty": bool(git("status", "--porcelain")),
    }


def versions() -> dict:
    packages = ["demandlab", "numpy", "pandas", "scikit-learn", "duckdb", "mlflow", "streamlit"]
    return {name: importlib.metadata.version(name) for name in packages}


def configure_tracking(root: Path, synthetic: bool = False):
    local = (root / "output" / "mlflow").resolve()
    local.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri("sqlite:///" + (local / "tracking.sqlite").as_posix())
    name = "DemandLab synthetic tests" if synthetic else "DemandLab UCI II"
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        mlflow.create_experiment(name, artifact_location=(local / "artifacts").as_uri())
    mlflow.set_experiment(name)


def record_run(root: Path, name: str, params: dict, scores: dict, files: list[Path]) -> str:
    synthetic = bool(params.get("synthetic", False))
    configure_tracking(root, synthetic)
    with mlflow.start_run(run_name=name) as run:
        mlflow.set_tags(
            {"dataset": params.get("dataset", "unknown"), "synthetic": str(synthetic).lower()}
        )
        mlflow.log_params(
            {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
        )
        mlflow.log_metrics(
            {
                k: float(v)
                for k, v in scores.items()
                if v is not None and isinstance(v, (int, float))
            }
        )
        for path in files:
            mlflow.log_artifact(str(path))
        return run.info.run_id


def update_run(root: Path, run_id: str, scores: dict, files: list[Path]):
    configure_tracking(root)
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics({k: float(v) for k, v in scores.items() if v is not None})
        for path in files:
            mlflow.log_artifact(str(path))
