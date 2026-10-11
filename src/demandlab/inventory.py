"""Finite-horizon inventory simulation; policy never receives future sales."""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


def _json_values(value: Any) -> Any:
    """Normalize pandas missing values and NumPy scalars to standard JSON values."""
    if isinstance(value, dict):
        return {key: _json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_values(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass(frozen=True)
class InventoryParameters:
    initial_stock: int = 0
    lead_time_days: int = 7
    review_period_days: int = 7
    safety_stock_units: int = 0
    holding_cost: float = 0.01
    order_cost: float = 5.0
    shortage_penalty: float = 1.0

    def validate(self) -> None:
        for name in ("initial_stock", "lead_time_days", "review_period_days", "safety_stock_units"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not 1 <= self.lead_time_days <= 21 or not 1 <= self.review_period_days <= 7:
            raise ValueError("Lead time must be 1–21 and review period 1–7 days")
        if self.lead_time_days + self.review_period_days > 28:
            raise ValueError("Lead time + review period must not exceed 28 days")
        for name in ("holding_cost", "order_cost", "shortage_penalty"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


def order_decision(
    forecast: tuple[float, ...],
    day: int,
    available: int,
    in_transit: int,
    parameters: InventoryParameters,
) -> tuple[int, int | None]:
    """Return order and target before today's sales are observed (days are 1-based)."""
    p = parameters
    if (day - 1) % p.review_period_days:
        return 0, None
    end = min(28, day + p.lead_time_days + p.review_period_days - 1)
    target = math.ceil(sum(forecast[day - 1 : end]) + p.safety_stock_units)
    quantity = max(0, target - available - in_transit) if day + p.lead_time_days <= 28 else 0
    return quantity, target


@dataclass
class SimulationResult:
    daily: pd.DataFrame
    summary: dict[str, float | int | None]
    parameters: InventoryParameters
    forecast: tuple[float, ...]
    sales: tuple[int, ...]

    def export_json(self, provenance: dict[str, Any]) -> str:
        return json.dumps(
            _json_values(
                {
                    "schema_version": 1,
                    "provenance": provenance,
                    "parameters": asdict(self.parameters),
                    "summary": self.summary,
                    "forecast": self.forecast,
                    "scenario_sales": self.sales,
                    "assumptions": ASSUMPTIONS,
                    "daily": self.daily.to_dict(orient="records"),
                }
            ),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    def export_csv(self, provenance: dict[str, Any]) -> str:
        frame = self.daily.copy()
        for key, value in {**provenance, **asdict(self.parameters)}.items():
            frame[key] = str(value)
        frame["assumptions"] = " | ".join(ASSUMPTIONS)
        return frame.to_csv(index=False)


ASSUMPTIONS = [
    "Fixed 28-day forecast issued at one historical origin; no future sales in policy.",
    "Receipts, review/order, sales, end-of-day holding costs, in that order.",
    "No initial pipeline; lost sales are not backordered; integer units.",
    "Target window truncates at day 28; orders arriving after day 28 are prohibited.",
    "Hypothetical GBP costs; no purchase cost, salvage valuation or optimization.",
    "Recorded sales are a scenario, not observed unconstrained demand or historic inventory.",
]


def simulate(forecast, sales, parameters: InventoryParameters) -> SimulationResult:
    """Execute 28 daily events against a separately supplied sales scenario."""
    parameters.validate()
    prediction = np.asarray(forecast, dtype=float)
    path = np.asarray(sales, dtype=float)
    if prediction.shape != (28,) or path.shape != (28,):
        raise ValueError("Forecast and sales must each contain exactly 28 days")
    if not np.isfinite(prediction).all() or (prediction < 0).any():
        raise ValueError("Forecast must be finite and nonnegative")
    if not np.isfinite(path).all() or (path < 0).any() or (path != np.floor(path)).any():
        raise ValueError("Scenario sales must be finite nonnegative integer units")
    fixed = tuple(float(x) for x in prediction)
    stock = parameters.initial_stock
    pipeline: dict[int, int] = {}
    records = []
    for day, demand in enumerate(path.astype(int), 1):
        received = pipeline.pop(day, 0)
        stock += received
        opening = stock
        order, target = order_decision(fixed, day, stock, sum(pipeline.values()), parameters)
        if order:
            pipeline[day + parameters.lead_time_days] = order
        served = min(stock, int(demand))
        lost = int(demand) - served
        stock -= served
        records.append(
            {
                "day": day,
                "forecast": fixed[day - 1],
                "sales": int(demand),
                "received": received,
                "opening_stock": opening,
                "target_stock": target,
                "ordered": order,
                "served": served,
                "unserved": lost,
                "ending_stock": stock,
                "pipeline_units": sum(pipeline.values()),
                "holding_cost_gbp": stock * parameters.holding_cost,
                "order_cost_gbp": (order > 0) * parameters.order_cost,
                "shortage_cost_gbp": lost * parameters.shortage_penalty,
            }
        )
    daily = pd.DataFrame(records)
    total = int(daily.sales.sum())
    summary = {
        "service_rate": float(daily.served.sum() / total) if total else None,
        "unserved_units": int(daily.unserved.sum()),
        "shortage_days": int((daily.unserved > 0).sum()),
        "mean_stock": float(daily.ending_stock.mean()),
        "ending_stock": stock,
        "pipeline_units": sum(pipeline.values()),
        "orders": int((daily.ordered > 0).sum()),
        "ordered_units": int(daily.ordered.sum()),
        "received_units": int(daily.received.sum()),
    }
    for key in ("holding_cost_gbp", "order_cost_gbp", "shortage_cost_gbp"):
        summary[key] = float(daily[key].sum())
    summary["total_cost_gbp"] = sum(
        summary[k] for k in ("holding_cost_gbp", "order_cost_gbp", "shortage_cost_gbp")
    )
    return SimulationResult(daily, summary, parameters, fixed, tuple(int(x) for x in path))
