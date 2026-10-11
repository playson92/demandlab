"""Independent hand balances and policy information-boundary tests."""

import json
from dataclasses import replace

import numpy as np
import pytest

from demandlab.inventory import InventoryParameters, simulate


def test_hand_calculated_timing_cost_and_balance():
    p = InventoryParameters(
        initial_stock=3,
        lead_time_days=1,
        review_period_days=1,
        holding_cost=0.5,
        order_cost=2,
        shortage_penalty=4,
    )
    result = simulate([2] * 28, [2, 3, 1] + [0] * 25, p)
    d = result.daily
    assert d.loc[:2, "ordered"].tolist() == [1, 2, 2]
    assert d.loc[:2, "received"].tolist() == [0, 1, 2]
    assert d.loc[:2, "ending_stock"].tolist() == [1, 0, 1]
    assert d.loc[:2, "unserved"].tolist() == [0, 1, 0]
    assert d.loc[:2, "holding_cost_gbp"].tolist() == [0.5, 0, 0.5]
    assert d.loc[:2, "order_cost_gbp"].tolist() == [2, 2, 2]
    assert d.loc[:2, "shortage_cost_gbp"].tolist() == [0, 4, 0]
    assert result.summary["ending_stock"] + d.served.sum() == p.initial_stock + d.received.sum()
    assert result.summary["ordered_units"] == result.summary["received_units"]
    assert result.summary["pipeline_units"] == 0


def test_lead_one_never_serves_order_day_and_no_backorders():
    result = simulate(
        [1] * 28, [3] + [0] * 27, InventoryParameters(lead_time_days=1, review_period_days=1)
    )
    assert result.daily.loc[0, "served"] == 0
    assert result.daily.loc[0, "unserved"] == 3
    assert result.daily.loc[1, "received"] == 2
    assert result.daily.loc[1, "ending_stock"] == 2
    assert result.summary["shortage_days"] == 1


def test_future_sales_cannot_change_prior_orders():
    p = InventoryParameters(initial_stock=10, lead_time_days=3, review_period_days=2)
    a = simulate([2] * 28, [1] * 28, p)
    b = simulate([2] * 28, [1] * 10 + [100] * 18, p)
    # Includes day 11 morning: that day's changed sales are not yet known.
    assert a.daily.loc[:10, "ordered"].tolist() == b.daily.loc[:10, "ordered"].tolist()
    assert a.daily.loc[:9, "ending_stock"].tolist() == b.daily.loc[:9, "ending_stock"].tolist()


def test_costs_do_not_change_policy():
    p = InventoryParameters(initial_stock=10)
    a = simulate([3] * 28, [2] * 28, p)
    b = simulate(
        [3] * 28, [2] * 28, replace(p, holding_cost=100, order_cost=0, shortage_penalty=1000)
    )
    assert a.daily.ordered.tolist() == b.daily.ordered.tolist()
    assert a.daily.ending_stock.tolist() == b.daily.ending_stock.tolist()
    assert a.summary["total_cost_gbp"] != b.summary["total_cost_gbp"]


def test_terminal_truncation_zero_sales_and_export():
    result = simulate(
        [0] * 28,
        [0] * 28,
        InventoryParameters(initial_stock=0, safety_stock_units=5, lead_time_days=7),
    )
    assert result.summary["service_rate"] is None
    assert result.summary["unserved_units"] == 0
    assert result.summary["shortage_days"] == 0
    assert result.daily.loc[21:, "ordered"].sum() == 0
    assert result.summary["pipeline_units"] == 0
    exported = json.loads(
        result.export_json({"sku": "ABC", "origin": "2011-11-10", "run_id": "example"})
    )
    assert exported["parameters"]["safety_stock_units"] == 5
    assert exported["provenance"]["sku"] == "ABC"
    assert len(exported["daily"]) == 28
    assert "scenario_sales" in exported
    assert "safety_stock_units" in result.export_csv({"sku": "ABC"})


def test_json_export_uses_null_for_nonreview_targets_and_native_parameters():
    result = simulate(
        [1] * 28, [0] * 28, InventoryParameters(initial_stock=np.int64(2), review_period_days=7)
    )

    def reject_nonstandard_constant(value):
        raise AssertionError(f"Nonstandard JSON numeric constant: {value}")

    exported = json.loads(
        result.export_json({"sku": "ABC"}), parse_constant=reject_nonstandard_constant
    )
    assert exported["daily"][1]["target_stock"] is None
    assert exported["daily"][0]["target_stock"] == 14
    assert exported["parameters"]["initial_stock"] == 2


@pytest.mark.parametrize(
    "forecast,sales,p",
    [
        ([1] * 27, [1] * 28, InventoryParameters()),
        ([np.nan] * 28, [1] * 28, InventoryParameters()),
        ([1] * 28, [0.5] * 28, InventoryParameters()),
        ([1] * 28, [1] * 28, InventoryParameters(initial_stock=-1)),
        ([1] * 28, [1] * 28, InventoryParameters(lead_time_days=0)),
    ],
)
def test_invalid_parameters(forecast, sales, p):
    with pytest.raises(ValueError):
        simulate(forecast, sales, p)
