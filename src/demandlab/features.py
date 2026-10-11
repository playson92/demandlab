"""Origin-anchored features for a shared direct 28-day forecasting model."""

import numpy as np
import pandas as pd

HORIZON = 28
LAGS = (0, 1, 6, 13, 27)
FEATURE_COLUMNS = [
    "horizon",
    "target_weekday",
    "target_month",
    "weekday_mean_4w",
    "days_since_positive",
    *[f"lag_{lag}" for lag in LAGS],
    *[f"{stat}_{window}" for window in (7, 28, 56) for stat in ("mean", "std", "zero_share")],
]


def clean_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Validate the public daily contract without inspecting future values."""
    result = daily[["sku", "date", "y"]].copy()
    result["sku"] = result["sku"].astype(str)
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    if result.duplicated(["sku", "date"]).any():
        raise ValueError("Duplicate SKU/date observations")
    if result["y"].isna().any() or not np.isfinite(result["y"]).all() or (result.y < 0).any():
        raise ValueError("Recorded units must be finite and nonnegative")
    return result.sort_values(["sku", "date"]).reset_index(drop=True)


def features_at(daily: pd.DataFrame, origin) -> pd.DataFrame:
    """Build 28 rows per eligible SKU using values observed by origin only.

    A SKU needs 56 observed calendar days. No values are invented before its
    first observed sale. Future rows are removed before validation or statistics.
    """
    origin = pd.Timestamp(origin).normalize()
    history = clean_daily(daily.loc[pd.to_datetime(daily.date) <= origin])
    blocks = []
    target_dates = pd.date_range(origin + pd.Timedelta(days=1), periods=HORIZON)
    for sku, group in history.groupby("sku", sort=True):
        if len(group) < 56:
            continue
        dates = pd.DatetimeIndex(group.date)
        if dates[-1] != origin or not dates.equals(pd.date_range(dates[0], origin)):
            raise ValueError(f"Incomplete daily calendar for {sku} at {origin.date()}")
        values = group.y.to_numpy(dtype=np.float64)
        known = {f"lag_{lag}": values[-1 - lag] for lag in LAGS}
        for window in (7, 28, 56):
            recent = values[-window:]
            known.update(
                {
                    f"mean_{window}": recent.mean(),
                    f"std_{window}": recent.std(),
                    f"zero_share_{window}": (recent == 0).mean(),
                }
            )
        positives = np.flatnonzero(values > 0)
        known["days_since_positive"] = (
            len(values) - 1 - positives[-1] if len(positives) else len(values)
        )
        weekdays = dates[-28:].dayofweek
        means = {day: values[-28:][weekdays == day].mean() for day in range(7)}
        block = pd.DataFrame(
            {
                "sku": sku,
                "origin": origin,
                "target_date": target_dates,
                "horizon": np.arange(1, 29),
                "scale": max(1.0, values[-28:].mean()),
                "target_weekday": target_dates.dayofweek,
                "target_month": target_dates.month,
                "weekday_mean_4w": [means[day] for day in target_dates.dayofweek],
                **known,
            }
        )
        blocks.append(block)
    if not blocks:
        raise ValueError("At least 56 known calendar days are required for an eligible SKU")
    result = pd.concat(blocks, ignore_index=True)
    result[FEATURE_COLUMNS] = result[FEATURE_COLUMNS].astype(np.float32)
    return result


def training_frame(daily: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Use weekly origins aligned to cutoff with all 28 labels already known."""
    cutoff = pd.Timestamp(cutoff).normalize()
    history = clean_daily(daily.loc[pd.to_datetime(daily.date) <= cutoff])
    earliest = history.date.min() + pd.Timedelta(days=55)
    latest = cutoff - pd.Timedelta(days=28)
    origins = []
    cursor = latest
    while cursor >= earliest:
        origins.append(cursor)
        cursor -= pd.Timedelta(days=7)
    blocks = []
    for origin in reversed(origins):
        try:
            blocks.append(features_at(history, origin))
        except ValueError as error:
            if "At least 56" not in str(error):
                raise
    if not blocks:
        raise ValueError("Insufficient history for fully observed training horizons")
    frame = pd.concat(blocks, ignore_index=True).merge(
        history.rename(columns={"date": "target_date"}),
        on=["sku", "target_date"],
        how="left",
        validate="many_to_one",
    )
    if frame.y.isna().any() or (frame.origin + pd.Timedelta(days=28) > cutoff).any():
        raise ValueError("Training labels must be fully observed by cutoff")
    return frame
