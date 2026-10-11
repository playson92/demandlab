"""Frozen baselines and one global categorical histogram boosting model."""

import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from demandlab.features import FEATURE_COLUMNS, clean_daily, features_at, training_frame

CONFIGS = {
    "A": dict(
        learning_rate=0.05,
        max_iter=150,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1.0,
    ),
    "B": dict(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=31,
        min_samples_leaf=30,
        l2_regularization=1.0,
    ),
    "C": dict(
        learning_rate=0.08,
        max_iter=150,
        max_leaf_nodes=15,
        min_samples_leaf=60,
        l2_regularization=5.0,
    ),
}
METHODS = ("seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting")


def forecast(daily: pd.DataFrame, origin, method: str, params=None) -> pd.DataFrame:
    """Issue all horizons at once; no within-window updates are possible."""
    started = time.perf_counter()
    origin = pd.Timestamp(origin).normalize()
    history = clean_daily(daily.loc[pd.to_datetime(daily.date) <= origin])
    features = features_at(history, origin)
    if method == "seasonal_naive_7":
        weeks = {sku: group.y.to_numpy()[-7:] for sku, group in history.groupby("sku")}
        prediction = np.array(
            [
                weeks[sku][(int(h) - 1) % 7]
                for sku, h in zip(features.sku, features.horizon, strict=True)
            ]
        )
    elif method == "weekday_mean_4w":
        prediction = features.weekday_mean_4w.to_numpy()
    elif method == "hist_gradient_boosting":
        train = training_frame(history, origin)
        categories = {sku: index for index, sku in enumerate(sorted(train.sku.unique()))}
        if len(categories) > 255:
            raise ValueError("Categorical SKU exceeds the model bin limit")

        def matrix(frame):
            return np.column_stack(
                [
                    frame.sku.map(categories).to_numpy(dtype=np.float32),
                    frame[FEATURE_COLUMNS].to_numpy(dtype=np.float32),
                ]
            )

        recipe = CONFIGS[params].copy() if isinstance(params, str) else dict(params or CONFIGS["A"])
        model = HistGradientBoostingRegressor(
            **recipe,
            loss="poisson",
            early_stopping=False,
            random_state=42,
            categorical_features=[True] + [False] * len(FEATURE_COLUMNS),
        )
        if train.y.sum() == 0:
            prediction = np.zeros(len(features))
        else:
            with threadpool_limits(limits=2):
                model.fit(matrix(train), train.y.to_numpy(dtype=np.float32))
                prediction = model.predict(matrix(features))
    else:
        raise ValueError(f"Unknown forecasting method: {method}")
    result = features[["sku", "origin", "target_date", "horizon", "scale"]].copy()
    result["method"] = method
    result["prediction"] = np.maximum(0, prediction)
    for column in ("q025", "q10", "q90", "q975"):
        result[column] = np.nan
    result.attrs["elapsed_seconds"] = time.perf_counter() - started
    result.attrs["threads"] = 2
    return result
