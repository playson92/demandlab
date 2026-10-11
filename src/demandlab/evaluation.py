"""Temporal protocol, pooled metrics, validation selection and calibration."""

import numpy as np
import pandas as pd

QUANTILES = {"q025": 0.025, "q10": 0.10, "q90": 0.90, "q975": 0.975}


def make_windows(end_date) -> list[dict]:
    """Return seven disjoint inclusive windows relative to the admitted last day."""
    end_date = pd.Timestamp(end_date).normalize()
    names = [f"validation_{i}" for i in range(1, 5)] + [
        "calibration_1",
        "calibration_2",
        "final_test",
    ]
    windows = []
    for index, name in enumerate(names):
        start = end_date - pd.Timedelta(days=195 - 28 * index)
        windows.append(
            dict(
                split=name,
                origin=start - pd.Timedelta(days=1),
                start=start,
                end=start + pd.Timedelta(days=27),
            )
        )
    return windows


def metrics(frame: pd.DataFrame) -> dict:
    """Compute pooled errors; zero denominators and absent quantiles yield None.

    Bias is percentage signed overprediction: 100 sum(prediction-y)/sum(abs(y)).
    Coverage is a fraction; width and pinball losses are in recorded units.
    """
    y = frame.y.to_numpy(dtype=float)
    prediction = frame.prediction.to_numpy(dtype=float)
    if not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError("Metrics require finite labels and predictions")
    denominator = np.abs(y).sum()
    errors = prediction - y
    result = {
        "n": len(y),
        "mae": float(np.abs(errors).mean()) if len(y) else None,
        "wape": float(100 * np.abs(errors).sum() / denominator) if denominator else None,
        "bias": float(100 * errors.sum() / denominator) if denominator else None,
    }
    for level, low, high in ((80, "q10", "q90"), (95, "q025", "q975")):
        available = (
            len(y) and low in frame and high in frame and frame[[low, high]].notna().all().all()
        )
        result[f"coverage{level}"] = None
        result[f"width{level}"] = None
        if available:
            lower, upper = frame[low].to_numpy(float), frame[high].to_numpy(float)
            if (
                not np.isfinite(lower).all()
                or not np.isfinite(upper).all()
                or (lower > upper).any()
            ):
                raise ValueError("Invalid prediction interval bounds")
            result[f"coverage{level}"] = float(((y >= lower) & (y <= upper)).mean())
            result[f"width{level}"] = float((upper - lower).mean())
    for column, probability in QUANTILES.items():
        available = len(y) and column in frame and frame[column].notna().all()
        result[f"pinball_{column}"] = None
        if available:
            residual = y - frame[column].to_numpy(float)
            result[f"pinball_{column}"] = float(
                np.maximum(probability * residual, (probability - 1) * residual).mean()
            )
    return result


def select_winner(scores) -> str:
    """Select pooled validation WAPE, retaining simplicity below 1% advantage.

    A mapping is assumed to contain already-pooled validation scores. A frame
    must contain only validation rows and candidate (or method) and wape.
    """
    if isinstance(scores, pd.DataFrame):
        if "split" in scores and not scores.split.astype(str).str.startswith("validation_").all():
            raise ValueError("Winner selection accepts validation results only")
        key = "candidate" if "candidate" in scores else "method"
        if scores[key].duplicated().any():
            raise ValueError("Pool absolute errors and actual units before choosing a winner")
        scores = dict(zip(scores[key], scores.wape, strict=True))
    valid = {
        name: float(value)
        for name, value in scores.items()
        if value is not None and np.isfinite(value)
    }
    if not valid:
        raise ValueError("No defined validation WAPE; report MAE and do not invent a winner")

    def complexity(name):
        return (0 if name == "seasonal_naive_7" else 1 if name == "weekday_mean_4w" else 2, name)

    best = min(valid, key=lambda name: (valid[name], complexity(name)))
    if valid[best] == 0:
        return min((name for name in valid if valid[name] == 0), key=complexity)
    for candidate in sorted(valid, key=complexity):
        if (valid[candidate] - valid[best]) / valid[candidate] < 0.01:
            return candidate
    return best


def calibrate(frame: pd.DataFrame, min_samples: int = 100) -> dict:
    """Fit signed normalized empirical quantiles from exactly two calibration splits."""
    if set(frame.split.unique()) != {"calibration_1", "calibration_2"}:
        raise ValueError("Calibration requires only calibration_1 and calibration_2")
    if min_samples < 1 or frame.empty:
        raise ValueError("Calibration needs a positive sample threshold and observations")
    if not frame.horizon.between(1, 28).all() or (frame.scale < 1).any():
        raise ValueError("Invalid calibration horizon or origin scale")
    work = frame.copy()
    work["residual"] = (work.y - work.prediction) / work.scale
    if not np.isfinite(work.residual).all():
        raise ValueError("Calibration residuals must be finite")
    work["bucket"] = ((work.horizon - 1) // 7).astype(int)
    result = {
        "schema_version": 1,
        "quantile_method": "linear",
        "min_samples": min_samples,
        "calibration_end": pd.to_datetime(frame.target_date).max().isoformat(),
        "methods": {},
    }
    for method, group in work.groupby("method", sort=True):
        buckets = {}
        for bucket in range(4):
            values = group.loc[group.bucket == bucket, "residual"]
            bucket_n = len(values)
            fallback = bucket_n < min_samples
            if fallback:
                values = group.residual
            quantiles = np.quantile(values, list(QUANTILES.values()), method="linear")
            buckets[str(bucket)] = {
                "n": len(values),
                "bucket_n": bucket_n,
                "source": "pooled_method" if fallback else "horizon_bucket",
                **dict(zip(QUANTILES, quantiles.tolist(), strict=True)),
            }
        result["methods"][method] = buckets
    return result


def apply_intervals(forecasts: pd.DataFrame, calibration: dict) -> pd.DataFrame:
    """Apply fixed quantiles only once both calibration windows are observed."""
    result = forecasts.copy()
    if (pd.to_datetime(result.origin) < pd.Timestamp(calibration["calibration_end"])).any():
        raise ValueError("Later calibration must not be applied to earlier origins")
    if not result.horizon.between(1, 28).all() or (result.scale < 1).any():
        raise ValueError("Invalid forecast horizon or origin scale")
    for column in QUANTILES:
        bounds = []
        for method, horizon, prediction, scale in zip(
            result.method, result.horizon, result.prediction, result.scale, strict=True
        ):
            quantile = calibration["methods"][method][str((int(horizon) - 1) // 7)][column]
            bounds.append(max(0.0, prediction + quantile * scale))
        result[column] = bounds
    ordered = result[list(QUANTILES)].to_numpy()
    if not np.isfinite(ordered).all() or (np.diff(ordered, axis=1) < 0).any():
        raise ValueError("Intervals must be finite, ordered and nested")
    return result
