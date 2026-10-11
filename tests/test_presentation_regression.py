"""Check presentation conventions and the inventory calculation boundary."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from artifacts import load_artifacts
from charts import forecast_chart, inventory_chart
from presentation import METHODS, display, method_label, method_table
from state import (
    changed_parameters,
    example_parameters,
    inventory_context,
    reset_parameters,
    synchronize_context,
)
from test_artifacts import artifacts as artifacts

from demandlab.inventory import InventoryParameters, simulate


def test_names_and_colors_remain_identical_in_tables_and_forecasts(artifacts):
    data = load_artifacts(artifacts)
    origin = pd.Timestamp(data["manifest"]["test_origin"])
    final = data["forecasts"].query("sku == 'A'").sort_values("horizon")
    history = data["daily"].query("sku == 'A' and date <= @origin")
    observed = data["actuals"].query("sku == 'A'")
    for band_method in METHODS:
        figure = forecast_chart(
            history, final, observed, origin, list(METHODS), band_method, "80%", True
        )
        by_name = {trace.name: trace for trace in figure.data}
        for method, (label, color, dash) in METHODS.items():
            assert by_name[label].line.color == color
            assert by_name[label].line.dash == dash
            assert method_label(method) == label
        bands = [trace for trace in figure.data if trace.fill == "tonexty"]
        assert len(bands) == 1
        color = METHODS[band_method][1]
        rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
        assert bands[0].fillcolor == f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.16)"
        assert by_name["Sprzedaż testowa"].line.color != "#ffffff"
    table = method_table(data["metrics"], ["mae", "wape", "bias"])
    assert set(table["Metoda"]) == {method_label(method) for method in METHODS}
    # Bias is already expressed in percent and must not be multiplied by 100.
    assert table["Bias [%]"].tolist() == data["metrics"].bias.tolist()


def test_null_and_zero_values_are_distinct():
    assert display(None, "%") == "N/A"
    assert display(np.nan, "%") == "N/A"
    assert display(0, "%") == "0,00%"
    assert display(-8.721407, "%") == "-8,72%"


@pytest.mark.parametrize("method", list(METHODS))
def test_loader_preserves_exact_inventory_inputs_and_results(artifacts, method):
    raw_forecasts = pd.read_parquet(artifacts / "forecasts.parquet")
    raw_actuals = pd.read_parquet(artifacts / "actuals.parquet")
    parameters = InventoryParameters(
        initial_stock=8,
        lead_time_days=2,
        review_period_days=3,
        safety_stock_units=4,
        holding_cost=0.25,
        order_cost=1.5,
        shortage_penalty=3,
    )
    forecast = (
        raw_forecasts.loc[raw_forecasts.sku.eq("A") & raw_forecasts.method.eq(method)]
        .sort_values("horizon")
        .prediction.to_numpy()
    )
    sales = raw_actuals.loc[raw_actuals.sku.eq("A")].sort_values("date").y.to_numpy()
    expected = simulate(forecast, sales, parameters)
    data = load_artifacts(artifacts)
    actual = simulate(
        data["forecasts"]
        .loc[data["forecasts"].sku.eq("A") & data["forecasts"].method.eq(method)]
        .sort_values("horizon")
        .prediction.to_numpy(),
        data["actuals"].loc[data["actuals"].sku.eq("A")].sort_values("date").y.to_numpy(),
        parameters,
    )
    pd.testing.assert_frame_equal(actual.daily, expected.daily)
    assert actual.summary == expected.summary
    provenance = {"sku": "A", "method": method, "origin": data["manifest"]["test_origin"]}
    assert actual.export_json(provenance) == expected.export_json(provenance)
    exported = json.loads(actual.export_json(provenance))
    assert exported["scenario_sales"] == sales.tolist()
    assert exported["parameters"]["lead_time_days"] == 2
    figure = inventory_chart(
        actual, data["actuals"].query("sku == 'A'").sort_values("date").date, method
    )
    assert list(figure.data[0].y) == expected.daily.ending_stock.tolist()
    assert (
        list(figure.data[0].x)
        == data["actuals"].query("sku == 'A'").sort_values("date").date.tolist()
    )


def test_sku_changes_reset_example_parameters_but_parameter_changes_keep_baseline():
    history_a = pd.DataFrame({"y": [2] * 28})
    history_b = pd.DataFrame({"y": [9] * 28})
    a = example_parameters(history_a)
    b = example_parameters(history_b)
    state = {}
    context_a = inventory_context("A", "2011-11-10", "weekday_mean_4w", [2] * 28)
    assert synchronize_context(state, "A", a, context_a)
    assert state["initial_stock"] == 14
    state["baseline"] = {"result": "saved A"}
    state["lead_time"] = 14
    assert not synchronize_context(state, "A", a, context_a)
    assert state["initial_stock"] == 14
    assert state["lead_time"] == 14
    assert "baseline" in state
    assert synchronize_context(
        state, "B", b, inventory_context("B", "2011-11-10", "weekday_mean_4w", [2] * 28)
    )
    assert state["initial_stock"] == 63
    assert state["lead_time"] == 7
    assert "baseline" not in state
    reset_parameters(state, a)
    assert state["initial_stock"] == 14


@pytest.mark.parametrize(
    "sku,origin,method,sales",
    [
        ("B", "2011-11-10", "weekday_mean_4w", [2] * 28),
        ("A", "2011-11-11", "weekday_mean_4w", [2] * 28),
        ("A", "2011-11-10", "hist_gradient_boosting", [2] * 28),
        ("A", "2011-11-10", "weekday_mean_4w", [3] * 28),
    ],
)
def test_changed_ab_context_discards_baseline(sku, origin, method, sales):
    parameters = InventoryParameters()
    state = {}
    original = inventory_context("A", "2011-11-10", "weekday_mean_4w", [2] * 28)
    synchronize_context(state, "A", parameters, original)
    state["baseline"] = "saved"
    synchronize_context(state, sku, parameters, inventory_context(sku, origin, method, sales))
    assert "baseline" not in state


def test_changed_parameters_discloses_only_actual_differences():
    a = InventoryParameters(initial_stock=20)
    b = replace(a, lead_time_days=14, holding_cost=0.5)
    assert changed_parameters(a, b) == {"lead_time_days": (7, 14), "holding_cost": (0.01, 0.5)}


def test_rendered_inventory_passes_exact_scenario_to_original_engine(artifacts, monkeypatch):
    import views
    from streamlit.testing.v1 import AppTest

    captures = []

    def audited_simulate(forecast, sales, parameters):
        result = simulate(forecast, sales, parameters)
        captures.append((np.array(forecast), np.array(sales), parameters, result))
        return result

    monkeypatch.setenv("DEMANDLAB_DEMO_DIR", str(artifacts))
    monkeypatch.setattr(views, "simulate", audited_simulate)
    entry = Path(__file__).resolve().parents[1] / "app/streamlit_app.py"
    app = AppTest.from_file(str(entry), default_timeout=20).run()
    assert not app.exception
    app.selectbox(key="method").set_value("hist_gradient_boosting").run()
    app.button(key="goto_inventory").click().run()
    assert not app.exception
    assert app.session_state["sku"] == "A"
    assert app.session_state["method"] == "hist_gradient_boosting"
    actuals = (
        pd.read_parquet(artifacts / "actuals.parquet")
        .query("sku == 'A'")
        .sort_values("date")
        .y.to_numpy()
    )
    for _, sales, _, _ in captures[-3:]:
        np.testing.assert_array_equal(sales, actuals)
    app.button(key="save_baseline").click().run()
    baseline = app.session_state["baseline"]
    app.number_input(key="lead_time").set_value(14).run()
    assert not app.exception
    assert app.session_state["baseline"]["context"] == baseline["context"]
    assert app.session_state["initial_stock"] == baseline["parameters"].initial_stock
    for _, sales, parameters, result in captures[-3:]:
        np.testing.assert_array_equal(sales, actuals)
        assert parameters.lead_time_days == 14
        assert parameters.initial_stock == baseline["parameters"].initial_stock
        expected = simulate(result.forecast, actuals, parameters)
        pd.testing.assert_frame_equal(result.daily, expected.daily)
        assert result.summary == expected.summary
    app.selectbox(key="scenario").set_value("reference").run()
    app.slider(key="multiplier").set_value(0.0).run()
    assert not app.exception
    assert "baseline" not in app.session_state
    assert app.metric[0].value == "N/A"
    for _, sales, _, _ in captures[-3:]:
        np.testing.assert_array_equal(sales, np.zeros(28))
