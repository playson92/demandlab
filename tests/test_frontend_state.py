# ruff: noqa: F811
"""State transitions tested through real widgets on explicit fixtures."""

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_app import APP, demo  # noqa: F401, F811

from demandlab.inventory import simulate


def test_ab_uses_existing_simulate_and_same_context(demo):
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="view").set_value("inventory").run()
    app.button(key="save_baseline").click().run()
    a = app.session_state["baseline"]
    app.number_input(key="lead_time").set_value(14).run()
    assert app.session_state["baseline"]["context"] == a["context"]
    p = a["parameters"]
    assert app.number_input(key="initial_stock").value == p.initial_stock
    direct = simulate(a["result"].forecast, a["result"].sales, p)
    assert direct.summary == a["summary"]
    pd.testing.assert_frame_equal(direct.daily, a["result"].daily)
    assert any("14" in c.value for c in app.caption)
    app.selectbox(key="method").set_value("hist_gradient_boosting").run()
    assert "baseline" not in app.session_state
    assert not app.exception


def test_sku_reset_and_explicit_restore(demo):
    daily = pd.read_parquet(demo / "daily.parquet")
    daily.loc[daily.sku == "B", "y"] = 8
    daily.to_parquet(demo / "daily.parquet")
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="view").set_value("inventory").run()
    app.number_input(key="initial_stock").set_value(99).run()
    app.number_input(key="lead_time").set_value(14).run()
    assert app.number_input(key="initial_stock").value == 99
    app.selectbox(key="sku").select("B").run()
    assert app.number_input(key="initial_stock").value == 56
    app.number_input(key="buffer").set_value(12).run()
    app.button(key="reset_parameters").click().run()
    assert app.number_input(key="buffer").value == 0
    assert app.number_input(key="lead_time").value == 7
    assert not app.exception


def test_url_roundtrip_and_invalid_input(demo):
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.query_params.update(view="inventory", sku="B", method="hist_gradient_boosting")
    app.run()
    assert app.session_state["view"] == "inventory"
    assert app.session_state["sku"] == "B"
    assert app.session_state["method"] == "hist_gradient_boosting"
    fresh = AppTest.from_file(str(APP), default_timeout=20)
    fresh.query_params.update(app.query_params)
    fresh.run()
    assert fresh.session_state["sku"] == "B"
    invalid = AppTest.from_file(str(APP), default_timeout=20)
    invalid.query_params.update(view="invalid", sku="missing", method="nonsense")
    invalid.run()
    assert not invalid.exception
    assert invalid.info


def test_scenario_mode_resets_ab_even_same_sales(demo):
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="view").set_value("inventory").run()
    app.button(key="save_baseline").click().run()
    app.selectbox(key="scenario").select("reference").run()
    assert "baseline" not in app.session_state
    assert not app.exception


def test_invalid_saved_report_has_friendly_error(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(APP.parent))
    import views

    reports = tmp_path / "reports"
    reports.mkdir()
    pd.DataFrame(
        [
            {
                "split": "final_test",
                "method": "weekday_mean_4w",
                "horizon": 1,
                "mae": 1,
                "wape": 5,
                "bias": 0,
            }
        ]
    ).to_csv(reports / "metrics_by_horizon.csv", index=False)
    messages = []
    monkeypatch.setattr(views.st, "error", messages.append)
    assert views.frozen_report(tmp_path, "metrics_by_horizon.csv").empty
    assert len(messages) == 1
    assert "metrics_by_horizon.csv" in messages[0]
