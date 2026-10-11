"""Manual metric checks and strict separation of selection/calibration/test."""

import numpy as np
import pandas as pd
import pytest

from demandlab.evaluation import apply_intervals, calibrate, make_windows, metrics, select_winner


def test_exact_disjoint_temporal_windows():
    end = pd.Timestamp("2011-12-08")
    windows = make_windows(end)
    assert windows[0]["start"] == end - pd.Timedelta(days=195)
    assert windows[-1]["end"] == end
    labels = []
    for window in windows:
        dates = pd.date_range(window["start"], window["end"])
        assert len(dates) == 28
        assert window["origin"] + pd.Timedelta(days=1) == window["start"]
        labels.extend(dates)
    assert len(set(labels)) == 196


def test_metrics_on_manually_computed_observations():
    frame = pd.DataFrame(
        {
            "y": [0, 10],
            "prediction": [2, 8],
            "q025": [0, 4],
            "q10": [1, 5],
            "q90": [3, 9],
            "q975": [4, 12],
        }
    )
    result = metrics(frame)
    assert result["n"] == 2
    assert result["mae"] == 2
    assert result["wape"] == 40
    assert result["bias"] == 0
    assert result["coverage80"] == 0
    assert result["coverage95"] == 1
    assert result["width80"] == 3
    assert result["width95"] == 6
    assert result["pinball_q10"] == pytest.approx(0.7)
    assert result["pinball_q90"] == pytest.approx(0.6)
    assert result["pinball_q025"] == pytest.approx(0.075)
    assert result["pinball_q975"] == pytest.approx(0.075)


def test_zero_denominator_and_unavailable_intervals_are_null():
    result = metrics(pd.DataFrame({"y": [0, 0], "prediction": [1, 2]}))
    assert result["wape"] is None
    assert result["bias"] is None
    assert result["mae"] == 1.5
    assert result["coverage80"] is None
    assert result["pinball_q90"] is None


def test_winner_simplicity_and_zero_wape():
    assert (
        select_winner({"seasonal_naive_7": 50, "hist_gradient_boosting_A": 49.6})
        == "seasonal_naive_7"
    )
    assert (
        select_winner({"seasonal_naive_7": 50, "hist_gradient_boosting_A": 49})
        == "hist_gradient_boosting_A"
    )
    assert (
        select_winner({"seasonal_naive_7": 0, "hist_gradient_boosting_A": 0}) == "seasonal_naive_7"
    )
    with pytest.raises(ValueError, match="validation"):
        select_winner(
            pd.DataFrame({"method": ["seasonal_naive_7"], "wape": [1], "split": ["final_test"]})
        )


def calibration_fixture():
    return pd.DataFrame(
        {
            "split": ["calibration_1", "calibration_2"],
            "method": ["seasonal_naive_7"] * 2,
            "horizon": [1, 8],
            "target_date": pd.to_datetime(["2020-03-01", "2020-03-29"]),
            "prediction": [10, 10],
            "y": [6, 14],
            "scale": [2, 2],
        }
    )


def test_signed_quantiles_pooled_fallback_and_no_retrospective_intervals():
    calibration = calibrate(calibration_fixture())
    bucket = calibration["methods"]["seasonal_naive_7"]["0"]
    assert bucket["source"] == "pooled_method"
    assert bucket["n"] == 2
    assert bucket["bucket_n"] == 1
    assert bucket["q10"] == pytest.approx(-1.6)
    future = pd.DataFrame(
        {
            "method": ["seasonal_naive_7"],
            "horizon": [1],
            "origin": [pd.Timestamp("2020-03-29")],
            "prediction": [1.0],
            "scale": [2.0],
        }
    )
    interval = apply_intervals(future, calibration)
    assert interval.q10.iloc[0] == 0
    assert interval.q90.iloc[0] == pytest.approx(4.2)
    assert (np.diff(interval[["q025", "q10", "q90", "q975"]]) >= 0).all()
    future["origin"] = pd.Timestamp("2020-03-28")
    with pytest.raises(ValueError, match="earlier"):
        apply_intervals(future, calibration)


def test_calibration_rejects_test_and_validation_labels():
    frame = calibration_fixture()
    frame.loc[1, "split"] = "final_test"
    with pytest.raises(ValueError, match="only calibration"):
        calibrate(frame)
