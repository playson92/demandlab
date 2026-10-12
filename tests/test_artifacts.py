"""Malformed presentation artifacts must fail before a join can lose observations."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.artifacts import METHODS, ArtifactError, artifact_version, load_artifacts


@pytest.fixture
def artifacts(tmp_path):
    origin = pd.Timestamp("2011-11-10")
    rows = [
        {
            "sku": sku,
            "origin": origin,
            "target_date": origin + pd.Timedelta(days=h),
            "horizon": h,
            "method": method,
            "prediction": float(h % 5),
            "q025": 0.0,
            "q10": 0.0,
            "q90": 6.0,
            "q975": 9.0,
            "split": "final_test",
            "run_id": "fixture",
        }
        for sku in ("A", "B")
        for method in sorted(METHODS)
        for h in range(1, 29)
    ]
    pd.DataFrame(rows).to_parquet(tmp_path / "forecasts.parquet")
    daily = pd.DataFrame(
        [
            {"sku": sku, "date": date, "y": date.day % 4}
            for sku in ("A", "B")
            for date in pd.date_range("2011-10-01", origin + pd.Timedelta(days=28))
        ]
    )
    daily.to_parquet(tmp_path / "daily.parquet")
    daily.loc[daily.date > origin].to_parquet(tmp_path / "actuals.parquet")
    pd.DataFrame(
        {"sku": ["A", "B"], "name": ["A name", "B name"], "group": ["regular", "intermittent"]}
    ).to_csv(tmp_path / "products.csv", index=False)
    pd.DataFrame(
        [
            {
                "split": split,
                "method": method,
                "mae": 1.0,
                "wape": 50.0,
                "bias": -10.0,
                "coverage80": 0.8,
                "width80": 6.0,
                "coverage95": 0.95,
                "width95": 9.0,
            }
            for split in ("validation", "final_test")
            for method in sorted(METHODS)
        ]
    ).to_csv(tmp_path / "metrics.csv", index=False)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "winner": "weekday_mean_4w",
                "source_sha": "test-fixture",
                "test_origin": str(origin),
                "D": "2011-12-08",
                "data_version": "fixture-version",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def rewrite(directory, table, transform):
    file = directory / f"{table}.parquet"
    transform(pd.read_parquet(file)).to_parquet(file)


def test_bundled_demo_and_source_manifest_are_accepted():
    directory = Path(__file__).resolve().parents[1] / "data/demo"
    data = load_artifacts(directory)
    assert data["manifest"] == json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert len(data["products"]) == 80
    assert len(data["actuals"]) == 80 * 28
    assert len(data["forecasts"]) == 80 * 3 * 28


@pytest.mark.parametrize("table", ["daily", "actuals", "forecasts"])
def test_missing_or_undeclared_sku_is_rejected(artifacts, table):
    rewrite(artifacts, table, lambda frame: frame.loc[frame.sku != "B"])
    with pytest.raises(ArtifactError, match="Zestaw SKU"):
        load_artifacts(artifacts)


def test_missing_method_for_one_sku_is_rejected(artifacts):
    rewrite(
        artifacts,
        "forecasts",
        lambda f: f.loc[~(f.sku.eq("B") & f.method.eq("hist_gradient_boosting"))],
    )
    with pytest.raises(ArtifactError, match="Każdy SKU"):
        load_artifacts(artifacts)


def test_missing_method_for_all_skus_is_rejected(artifacts):
    rewrite(artifacts, "forecasts", lambda f: f.loc[f.method != "hist_gradient_boosting"])
    with pytest.raises(ArtifactError, match="wymaganych metod"):
        load_artifacts(artifacts)


def test_origin_must_match_manifest_even_if_forecast_grid_is_consistent(artifacts):
    def shift(frame):
        frame["origin"] += pd.Timedelta(days=1)
        frame["target_date"] += pd.Timedelta(days=1)
        return frame

    rewrite(artifacts, "forecasts", shift)
    with pytest.raises(ArtifactError, match="Origin prognoz"):
        load_artifacts(artifacts)


@pytest.mark.parametrize(
    "table,expected",
    [("actuals", "pełne 28 dni"), ("forecasts", "pełne 28 dni"), ("daily", "ciągła")],
)
def test_single_missing_day_is_rejected(artifacts, table, expected):
    rewrite(artifacts, table, lambda f: f.drop(f.index[10]))
    with pytest.raises(ArtifactError, match=expected):
        load_artifacts(artifacts)


def test_actuals_shifted_dates_are_rejected(artifacts):
    def shift(frame):
        frame["date"] += pd.Timedelta(days=1)
        return frame

    rewrite(artifacts, "actuals", shift)
    with pytest.raises(ArtifactError, match="dokładnie origin"):
        load_artifacts(artifacts)


def test_actuals_disagreement_with_daily_is_rejected(artifacts):
    def alter(frame):
        frame.loc[frame.index[0], "y"] += 1
        return frame

    rewrite(artifacts, "actuals", alter)
    with pytest.raises(ArtifactError, match="nie jest zgodna"):
        load_artifacts(artifacts)


@pytest.mark.parametrize(
    "table,column",
    [("actuals", "y"), ("daily", "y"), ("forecasts", "prediction"), ("forecasts", "q975")],
)
def test_nonfinite_values_are_rejected(artifacts, table, column):
    def alter(frame):
        frame[column] = frame[column].astype(float)
        frame.loc[frame.index[0], column] = np.inf
        return frame

    rewrite(artifacts, table, alter)
    with pytest.raises(ArtifactError):
        load_artifacts(artifacts)


@pytest.mark.parametrize(
    "content", ["[]", "null", '{"schema_version": 999}', '{"schema_version": 1}', "{broken"]
)
def test_invalid_manifest_has_clean_polish_error(artifacts, content):
    (artifacts / "manifest.json").write_text(content, encoding="utf-8")
    with pytest.raises(ArtifactError) as error:
        load_artifacts(artifacts)
    assert "Traceback" not in str(error.value)
    assert "Ã" not in str(error.value)


def test_missing_demo_advice_restores_bundle_without_training(tmp_path):
    for loader in (artifact_version, load_artifacts):
        with pytest.raises(ArtifactError, match="Przywróć komplet plików") as error:
            loader(tmp_path)
        assert "python -m demandlab demo" not in str(error.value)


def test_missing_intervals_remain_missing_without_fake_zeros(artifacts):
    def alter(frame):
        frame[["q025", "q10", "q90", "q975"]] = np.nan
        return frame

    rewrite(artifacts, "forecasts", alter)
    assert load_artifacts(artifacts)["forecasts"].q10.isna().all()


def test_metrics_missing_method_in_one_split_is_rejected(artifacts):
    file = artifacts / "metrics.csv"
    metrics = pd.read_csv(file)
    metrics.drop(metrics.index[0]).to_csv(file, index=False)
    with pytest.raises(ArtifactError, match="niekompletne metody"):
        load_artifacts(artifacts)


def test_nonfinite_bias_is_rejected_without_changing_percent_unit(artifacts):
    file = artifacts / "metrics.csv"
    metrics = pd.read_csv(file)
    metrics.loc[0, "bias"] = np.inf
    metrics.to_csv(file, index=False)
    with pytest.raises(ArtifactError, match="nieskończone"):
        load_artifacts(artifacts)
