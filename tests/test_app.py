"""AppTest checks UI paths against explicit test-only artifact fixtures."""

import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app/streamlit_app.py"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    origin = pd.Timestamp("2011-11-10")
    rows = []
    for sku in ["A", "B"]:
        for method in ["seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting"]:
            for h in range(1, 29):
                rows.append(
                    {
                        "sku": sku,
                        "origin": origin,
                        "target_date": origin + pd.Timedelta(days=h),
                        "horizon": h,
                        "method": method,
                        "prediction": 2.0,
                        "q025": 0.0,
                        "q10": 1.0,
                        "q90": 3.0,
                        "q975": 4.0,
                        "split": "final_test",
                        "run_id": "test-only",
                    }
                )
    pd.DataFrame(rows).to_parquet(tmp_path / "forecasts.parquet")
    pd.DataFrame(
        [
            {"sku": s, "date": d, "y": 2}
            for s in ["A", "B"]
            for d in pd.date_range("2011-08-01", origin)
        ]
    ).to_parquet(tmp_path / "daily.parquet")
    pd.DataFrame(
        [
            {"sku": s, "date": origin + pd.Timedelta(days=h), "y": 2}
            for s in ["A", "B"]
            for h in range(1, 29)
        ]
    ).to_parquet(tmp_path / "actuals.parquet")
    pd.DataFrame(
        {
            "sku": ["A", "B"],
            "name": ["Test regular", "Test intermittent"],
            "group": ["regular", "intermittent"],
        }
    ).to_csv(tmp_path / "products.csv", index=False)
    pd.DataFrame(
        [
            {
                "split": split,
                "method": method,
                "mae": 0.0,
                "wape": 0.0,
                "coverage80": 1.0,
                "width80": 2.0,
                "coverage95": 1.0,
                "width95": 4.0,
            }
            for split in [
                "validation_1",
                "validation_2",
                "validation_3",
                "validation_4",
                "final_test",
            ]
            for method in ["seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting"]
        ]
    ).to_csv(tmp_path / "metrics.csv", index=False)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "winner": "seasonal_naive_7",
                "source_sha": "test-fixture",
                "test_origin": str(origin.date()),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEMANDLAB_DEMO_DIR", str(tmp_path))
    return tmp_path


def test_three_views_and_real_widget_interactions(demo):
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    app.selectbox(key="sku").select("B").run()
    app.selectbox(key="method").select("weekday_mean_4w").run()
    app.selectbox(key="interval").select("95%").run()
    assert set(app.dataframe[0].value.method) == {"weekday_mean_4w"}
    app.button(key="goto_inventory").click().run()
    assert app.session_state["sku"] == "B"
    assert app.session_state["method"] == "weekday_mean_4w"
    app.number_input(key="lead_time").set_value(1).run()
    app.number_input(key="initial_stock").set_value(0).run()
    assert not app.exception
    assert next(d.value for d in app.dataframe if "served" in d.value).loc[0, "served"] == "0"
    app.selectbox(key="scenario").select("reference").run()
    app.slider(key="multiplier").set_value(0.0).run()
    assert not app.exception
    assert app.metric[0].value == "N/A"
    app.radio(key="view").set_value("methods").run()
    assert not app.exception
    assert not any(e.label.startswith("Test ") for e in app.expander)
    app.selectbox(key="evaluation_stage").select("final_test").run()
    assert not app.exception
    assert any(e.label.startswith("Test ") for e in app.expander)


def test_invalid_artifact_version_is_friendly(demo):
    (demo / "manifest.json").write_text('{"schema_version": 999}', encoding="utf-8")
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert "Niezgodna wersja" in app.error[0].value


def test_missing_demo_is_friendly(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDLAB_DEMO_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert "Brakuje" in app.error[0].value


def test_corrupted_forecast_is_friendly(demo):
    forecast = pd.read_parquet(demo / "forecasts.parquet")
    forecast.loc[0, "prediction"] = -1
    forecast.to_parquet(demo / "forecasts.parquet")
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert "nieujemne" in app.error[0].value
