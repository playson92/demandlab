"""Tests protect origin anchoring, full label availability and baseline semantics."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from demandlab.features import features_at, training_frame
from demandlab.forecasting import CONFIGS, forecast


def daily_fixture(days=180):
    dates = pd.date_range("2020-01-01", periods=days)
    return pd.DataFrame({"sku": "A", "date": dates, "y": np.arange(1, days + 1)})


def test_baselines_repeat_known_week_for_later_horizons():
    daily = daily_fixture()
    origin = daily.date.iloc[99]
    naive = forecast(daily, origin, "seasonal_naive_7")
    mean = forecast(daily, origin, "weekday_mean_4w")
    assert len(naive) == 28
    assert naive.prediction.iloc[7] == 94
    assert naive.prediction.iloc[19] == 99
    assert mean.prediction.iloc[7] == 83.5
    assert mean.prediction.iloc[19] == 88.5
    assert naive.target_date.iloc[-1] == origin + pd.Timedelta(days=28)
    assert naive[["q025", "q10", "q90", "q975"]].isna().all().all()


@pytest.mark.parametrize(
    "method", ["seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting"]
)
def test_future_mutation_and_truncation_leave_forecast_unchanged(method):
    daily = daily_fixture()
    origin = daily.date.iloc[129]
    modified = daily.copy()
    modified.loc[modified.date > origin, "y"] = -99999
    params = dict(CONFIGS["A"], max_iter=5)
    full = forecast(daily, origin, method, params)
    altered = forecast(modified, origin, method, params)
    truncated = forecast(daily[daily.date <= origin], origin, method, params)
    assert_frame_equal(full, altered)
    assert_frame_equal(full, truncated)
    assert_frame_equal(features_at(daily, origin), features_at(modified, origin))


def test_training_origins_require_all_labels_and_weekly_alignment():
    daily = daily_fixture()
    cutoff = daily.date.iloc[139]
    train = training_frame(daily, cutoff)
    assert (train.origin + pd.Timedelta(days=28) <= cutoff).all()
    assert (train.target_date <= cutoff).all()
    assert ((cutoff - train.origin).dt.days % 7 == 0).all()
    assert train.groupby(["sku", "origin"]).size().eq(28).all()
    modified = daily.copy()
    modified.loc[modified.date > cutoff, "y"] = 999999
    assert_frame_equal(train, training_frame(modified, cutoff))


def test_features_do_not_invent_pre_observation_days():
    daily = daily_fixture(55)
    with pytest.raises(ValueError, match="56"):
        features_at(daily, daily.date.max())
