"""Isolated actual stage orchestration with synthetic data, never portfolio results."""

import json

import numpy as np
import pandas as pd
import pytest

from demandlab import pipeline


def test_ordered_pipeline_freeze_integrity_and_local_tracking(tmp_path, monkeypatch):
    root = tmp_path
    for directory in ["data/processed", "reports", "configs"]:
        (root / directory).mkdir(parents=True)
    dates = pd.date_range("2009-12-01", periods=740)
    daily = pd.concat(
        [
            pd.DataFrame({"sku": sku, "date": dates, "y": (np.arange(len(dates)) % 7 + 1) * factor})
            for sku, factor in [("A", 1), ("B", 2)]
        ],
        ignore_index=True,
    )
    daily.to_parquet(root / "data/processed/daily.parquet", index=False)
    pipeline.dump(
        root / "reports/data_manifest.json",
        {
            "dataset": "synthetic test fixture",
            "synthetic": True,
            "source_sha256": "fixture",
        },
    )
    pipeline.dump(root / "configs/protocol.json", {"D": str(dates[-1].date())})
    pd.DataFrame(
        {
            "sku": ["A", "B"],
            "name": ["A", "B"],
            "group": ["regular", "intermittent"],
            "initial_units": [100, 200],
        }
    ).to_csv(root / "reports/product_selection.csv", index=False)
    monkeypatch.setattr(
        pipeline,
        "CONFIGS",
        {key: dict(value, max_iter=2) for key, value in pipeline.CONFIGS.items()},
    )
    chosen = pipeline.validate(root)
    assert chosen["winner"] == "seasonal_naive_7"
    pipeline.calibration(root)
    with pytest.raises(ValueError, match="review"):
        pipeline.freeze(root)
    (root / "reports/methodology_review.md").write_text("APPROVED_FOR_FINAL_TEST synthetic only")
    pipeline.freeze(root)
    predictions = pd.read_parquet(root / "output/final_test_predictions.parquet")
    assert "y" not in predictions
    assert len(predictions) == 2 * 28 * 3
    assert predictions[pipeline.QUANTILES].notna().all().all()
    pipeline.freeze(root)  # Complete replay preserves forecast bytes.
    scores = pipeline.final_test(root)
    assert len(scores) == 3 and scores[1]["mae"] == 0
    pipeline.build_demo(root)
    assert (root / "data/demo/manifest.json").exists()
    assert (root / "output/mlflow/tracking.sqlite").exists()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(
        tracking_uri="sqlite:///" + (root / "output/mlflow/tracking.sqlite").as_posix()
    )
    experiment = client.get_experiment_by_name("DemandLab synthetic tests")
    runs = client.search_runs(experiment.experiment_id)
    assert len(runs) == 29
    assert all(run.data.tags["synthetic"] == "true" for run in runs)
    original_execution = (root / "reports/test_execution.json").read_bytes()
    pipeline.validate(root, replay=True)
    pipeline.calibration(root, replay=True)
    pipeline.final_test(root)
    assert (root / "reports/test_execution.json").read_bytes() == original_execution
    assert (
        "already exposed" in pipeline.load(root / "output/replay_execution.json")["evaluation_kind"]
    )
    with pytest.raises(ValueError, match="calibration after freeze"):
        pipeline.calibration(root)
    recipe_path = root / "reports/model_selection.json"
    recipe = json.loads(recipe_path.read_text())
    recipe["winner"] = "hist_gradient_boosting"
    pipeline.dump(recipe_path, recipe)
    with pytest.raises(ValueError, match="recipe or calibration"):
        pipeline.final_test(root)
