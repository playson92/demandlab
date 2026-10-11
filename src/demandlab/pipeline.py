"""Ordered experiment stages: select, calibrate, freeze, then reveal test labels."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from demandlab.evaluation import apply_intervals, calibrate, make_windows, metrics, select_winner
from demandlab.forecasting import CONFIGS, forecast
from demandlab.tracking import code_identity, record_run, update_run, versions

METHODS = ["seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting"]
QUANTILES = ["q025", "q10", "q90", "q975"]


def dump(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False), encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def context(root: Path):
    daily = pd.read_parquet(root / "data/processed/daily.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    manifest = load(root / "reports/data_manifest.json")
    protocol = load(root / "configs/protocol.json")
    windows = make_windows(protocol["D"])
    return daily, manifest, windows


def join_labels(predictions: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    result = predictions.merge(
        daily.rename(columns={"date": "target_date"}),
        on=["sku", "target_date"],
        how="left",
        validate="many_to_one",
    )
    if result["y"].isna().any():
        raise ValueError("Missing outcome labels; evaluation refuses incomplete windows")
    return result


def issue(
    root: Path,
    daily: pd.DataFrame,
    window: dict,
    method: str,
    params: dict | None = None,
    candidate: str | None = None,
) -> pd.DataFrame:
    start = time.perf_counter()
    before = time.process_time()
    origin = pd.Timestamp(window["origin"])
    frame = forecast(daily, origin, method, params)
    frame["method"] = method
    frame["split"] = window["split"]
    frame["candidate"] = candidate or method
    frame["run_id"] = "pending"
    frame["schema_version"] = 1
    for col in QUANTILES:
        frame[col] = np.nan
    expected = daily.loc[daily.date <= origin, "sku"].nunique() * 28
    if len(frame) != expected or frame.duplicated(["sku", "target_date"]).any():
        raise ValueError("Forecast contract violation: expected exactly 28 rows per SKU")
    directory = root / "output/forecasts"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{window['split']}_{candidate or method}.parquet"
    frame.to_parquet(path, index=False)  # Outcomes are not joined before this write.
    timing = {
        "elapsed_seconds": time.perf_counter() - start,
        "cpu_seconds": time.process_time() - before,
        "rss_mb": psutil.Process().memory_info().rss / 1024**2,
    }
    params_log = {
        "method": method,
        "candidate": candidate or method,
        "split": window["split"],
        "origin": str(origin.date()),
        "seed": 42,
        "threads": 2,
        "model_params": params or {},
        **code_identity(root),
    }
    data_manifest = load(root / "reports/data_manifest.json")
    params_log.update(
        {
            "dataset": data_manifest["dataset"],
            "synthetic": data_manifest.get("synthetic", False),
            "data_sha256": data_manifest["source_sha256"],
            "sku_count": expected // 28,
        }
    )
    scores = metrics(join_labels(frame, daily)) if window["split"] != "final_test" else {}
    run_id = record_run(root, path.stem, params_log, {**scores, **timing}, [path])
    frame["run_id"] = run_id
    frame.to_parquet(path, index=False)
    update_run(root, run_id, {}, [path])
    resource_path = root / "reports/resources.json"
    resources = load(resource_path) if resource_path.exists() else {}
    resources[path.stem] = timing
    dump(resource_path, resources)
    print(f"{window['split']} {candidate or method}: {timing['elapsed_seconds']:.1f}s", flush=True)
    return frame


def validate(root: Path):
    if (root / "reports/freeze_manifest.json").exists():
        raise ValueError("Experiment already frozen; use a new output root for a new study")
    daily, manifest, windows = context(root)
    candidates = [(m, m, None) for m in METHODS[:2]] + [
        (f"hist_gradient_boosting_{key}", METHODS[2], value) for key, value in CONFIGS.items()
    ]
    frames = []
    rows = []
    for window in windows[:4]:
        for candidate, method, params in candidates:
            predictions = issue(root, daily, window, method, params, candidate)
            evaluated = join_labels(predictions, daily)
            rows.append(
                {
                    "split": window["split"],
                    "method": method,
                    "candidate": candidate,
                    **metrics(evaluated),
                }
            )
            frames.append(evaluated)
    evaluated = pd.concat(frames, ignore_index=True)
    scores = {
        candidate: metrics(part)["wape"] for candidate, part in evaluated.groupby("candidate")
    }
    best_tree = min((c for c in scores if c.startswith("hist_gradient")), key=lambda c: scores[c])
    family_scores = {m: scores[m] for m in METHODS[:2]} | {METHODS[2]: scores[best_tree]}
    winner = select_winner(family_scores)
    recipe = {
        "winner": winner,
        "tree_candidate": best_tree,
        "tree_params": CONFIGS[best_tree.rsplit("_", 1)[-1]],
        "validation_wape": family_scores,
        "candidate_wape": scores,
        "selection_rule": "<1% relative advantage does not justify a more complex family",
        "source_sha256": manifest.get("source_sha256"),
        "code": code_identity(root),
        "frozen_at": datetime.now(UTC).isoformat(),
    }
    dump(root / "reports/model_selection.json", recipe)
    pd.DataFrame(rows).to_csv(root / "reports/validation_candidates.csv", index=False)
    selected = evaluated[
        (evaluated.candidate.isin(METHODS[:2])) | (evaluated.candidate == best_tree)
    ]
    selected.to_parquet(root / "output/validation_evaluated.parquet", index=False)
    print(json.dumps(recipe, indent=2), flush=True)
    return recipe


def calibration(root: Path):
    if (root / "reports/freeze_manifest.json").exists():
        raise ValueError("Cannot change calibration after freeze")
    daily, _, windows = context(root)
    recipe = load(root / "reports/model_selection.json")
    frames = []
    for window in windows[4:6]:
        for method in METHODS:
            predictions = issue(
                root, daily, window, method, recipe["tree_params"] if method == METHODS[2] else None
            )
            frames.append(join_labels(predictions, daily))
    evaluated = pd.concat(frames, ignore_index=True)
    parameters = calibrate(evaluated)
    dump(root / "reports/calibration.json", parameters)
    evaluated.to_parquet(root / "output/calibration_evaluated.parquet", index=False)
    return parameters


def freeze(root: Path):
    daily, data_manifest, windows = context(root)
    review = root / "reports/methodology_review.md"
    if not review.exists() or "APPROVED_FOR_FINAL_TEST" not in review.read_text(encoding="utf-8"):
        raise ValueError("Independent methodology review must approve before final test")
    manifest_path = root / "reports/freeze_manifest.json"
    if manifest_path.exists() and (root / "reports/forecast_manifest.json").exists():
        saved = load(root / "reports/forecast_manifest.json")
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != saved["freeze_sha256"]:
            raise ValueError("Existing freeze changed")
        return load(manifest_path)
    recipe = load(root / "reports/model_selection.json")
    parameters = load(root / "reports/calibration.json")
    selection = pd.read_csv(root / "reports/product_selection.csv", dtype={"sku": str})
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "source": data_manifest,
        "skus": selection.sku.tolist(),
        "target": "daily_recorded_sales_units",
        "windows": windows,
        "recipe": recipe,
        "calibration": parameters,
        "seed": 42,
        "versions": versions(),
        "code": code_identity(root),
        "features": "Origin anchored lags, 7/28/56 statistics, weekday history, SKU, horizon, known calendar",
        "training_rule": "weekly origins aligned to evaluation origin; origin+28<=cutoff",
        "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "daily_sha256": hashlib.sha256(
            (root / "data/processed/daily.parquet").read_bytes()
        ).hexdigest(),
        "selection_sha256": hashlib.sha256(
            (root / "reports/product_selection.csv").read_bytes()
        ).hexdigest(),
        "final_test_exposed": False,
    }
    if manifest_path.exists():
        existing = load(manifest_path)
        for key in ("recipe", "calibration", "daily_sha256", "selection_sha256"):
            if existing[key] != manifest[key]:
                raise ValueError("Interrupted freeze inputs changed; do not overwrite evidence")
        if existing["code"]["working_tree_sha256"] != manifest["code"]["working_tree_sha256"]:
            raise ValueError("Interrupted freeze code changed")
        manifest = existing
    else:
        dump(manifest_path, manifest)  # Freeze precedes test forecasting and scoring.
    predictions = []
    for method in METHODS:
        saved_path = root / "output/forecasts" / f"final_test_{method}.parquet"
        frame = (
            pd.read_parquet(saved_path)
            if saved_path.exists()
            else issue(
                root,
                daily,
                windows[-1],
                method,
                recipe["tree_params"] if method == METHODS[2] else None,
            )
        )
        predictions.append(apply_intervals(frame, parameters))
    frozen = pd.concat(predictions, ignore_index=True)
    frozen.to_parquet(root / "output/final_test_predictions.parquet", index=False)
    dump(
        root / "reports/forecast_manifest.json",
        {
            "schema_version": 1,
            "origin": windows[-1]["origin"],
            "prediction_sha256": hashlib.sha256(
                (root / "output/final_test_predictions.parquet").read_bytes()
            ).hexdigest(),
            "freeze_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "code": code_identity(root),
        },
    )
    return manifest


def final_test(root: Path):
    daily, _, _ = context(root)
    forecast_manifest = load(root / "reports/forecast_manifest.json")
    freeze_path = root / "reports/freeze_manifest.json"
    if hashlib.sha256(freeze_path.read_bytes()).hexdigest() != forecast_manifest["freeze_sha256"]:
        raise ValueError("Freeze manifest has changed")
    frozen = load(freeze_path)
    if frozen["recipe"] != load(root / "reports/model_selection.json") or frozen[
        "calibration"
    ] != load(root / "reports/calibration.json"):
        raise ValueError("Frozen recipe or calibration has changed")
    if (
        frozen["source"]["source_sha256"]
        != load(root / "reports/data_manifest.json")["source_sha256"]
    ):
        raise ValueError("Source identity has changed")
    for relative, key in [
        ("data/processed/daily.parquet", "daily_sha256"),
        ("reports/product_selection.csv", "selection_sha256"),
    ]:
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != frozen[key]:
            raise ValueError("Frozen data or product selection has changed")
    if code_identity(root)["working_tree_sha256"] != frozen["code"]["working_tree_sha256"]:
        raise ValueError(
            "Modeling code/protocol changed after freeze; preserve results and declare post-test correction"
        )
    predictions_path = root / "output/final_test_predictions.parquet"
    if (
        hashlib.sha256(predictions_path.read_bytes()).hexdigest()
        != forecast_manifest["prediction_sha256"]
    ):
        raise ValueError("Frozen predictions have changed")
    evaluated = join_labels(pd.read_parquet(predictions_path), daily)
    evaluated.to_parquet(root / "output/final_test_evaluated.parquet", index=False)
    rows = [
        {"split": "final_test", "method": method, **metrics(part)}
        for method, part in evaluated.groupby("method")
    ]
    for method, part in evaluated.groupby("method"):
        update_run(root, part.run_id.iloc[0], metrics(part), [predictions_path, freeze_path])
    pd.DataFrame(rows).to_csv(root / "reports/final_test_metrics.csv", index=False)
    dump(
        root / "reports/test_execution.json",
        {
            "executed_utc": datetime.now(UTC).isoformat(),
            "forecast_manifest": forecast_manifest,
            "evaluation_kind": "frozen independent final test; recipe unchanged",
        },
    )
    print(pd.DataFrame(rows).to_string(index=False), flush=True)
    return rows


def build_demo(root: Path):
    daily, manifest, windows = context(root)
    recipe = load(root / "reports/model_selection.json")
    demo = root / "data/demo"
    demo.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(demo / "daily.parquet", index=False)
    test = pd.read_parquet(root / "output/final_test_evaluated.parquet")
    test.drop(columns="y").to_parquet(demo / "forecasts.parquet", index=False)
    daily[daily.date > pd.Timestamp(windows[-1]["origin"])].to_parquet(
        demo / "actuals.parquet", index=False
    )
    selection = pd.read_csv(root / "reports/product_selection.csv", dtype={"sku": str})
    selection.to_csv(demo / "products.csv", index=False)
    validation = pd.read_parquet(root / "output/validation_evaluated.parquet")
    combined = []
    for method, part in validation.groupby("method"):
        combined.append({"split": "validation", "method": method, **metrics(part)})
    combined += pd.read_csv(root / "reports/final_test_metrics.csv").to_dict("records")
    pd.DataFrame(combined).to_csv(demo / "metrics.csv", index=False)
    examples = {
        str(group): part.sort_values(["initial_units", "sku"], ascending=[False, True]).iloc[0].sku
        for group, part in selection.groupby("group")
    }
    dump(
        demo / "manifest.json",
        {
            "schema_version": 1,
            "winner": recipe["winner"],
            "source_sha": load(root / "reports/freeze_manifest.json")["code"]["source_sha"],
            "source_sha256": manifest.get("source_sha256"),
            "test_origin": windows[-1]["origin"],
            "D": windows[-1]["end"],
            "dataset": "UCI Online Retail II 502",
            "examples": examples,
            "data_version": hashlib.sha256((demo / "forecasts.parquet").read_bytes()).hexdigest(),
        },
    )
    dimensions = ["horizon", "sku"]
    for dimension in dimensions:
        rows = [
            {dimension: key[1], "method": key[0], **metrics(part)}
            for key, part in test.groupby(["method", dimension])
        ]
        pd.DataFrame(rows).to_csv(demo / f"metrics_by_{dimension}.csv", index=False)
    grouped = test.merge(selection[["sku", "group"]], on="sku", validate="many_to_one")
    rows = [
        {"group": key[1], "method": key[0], **metrics(part)}
        for key, part in grouped.groupby(["method", "group"])
    ]
    pd.DataFrame(rows).to_csv(root / "reports/metrics_by_regularity.csv", index=False)
    pd.DataFrame(combined).to_csv(root / "reports/metrics.csv", index=False)
