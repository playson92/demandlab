"""Pure context and parameter helpers, independent of widget rendering."""

import hashlib
from dataclasses import asdict

import numpy as np

from demandlab.inventory import InventoryParameters

PARAMETER_KEYS = {
    "initial_stock": "initial_stock",
    "lead_time": "lead_time_days",
    "review_period": "review_period_days",
    "buffer": "safety_stock_units",
    "holding": "holding_cost",
    "order_cost": "order_cost",
    "shortage": "shortage_penalty",
}


def example_parameters(history):
    stock = int(np.ceil(history.tail(28).y.mean() * 7)) if len(history) else 0
    return InventoryParameters(initial_stock=stock)


def reset_parameters(state, parameters):
    values = asdict(parameters)
    for key, field in PARAMETER_KEYS.items():
        state[key] = values[field]


def inventory_context(sku, origin, method, sales):
    path_hash = hashlib.sha256(np.asarray(sales, dtype="<i8").tobytes()).hexdigest()
    return (sku, str(origin), method, path_hash)


def synchronize_context(state, sku, parameters, context):
    """SKU resets example inputs; any changed A/B context clears the baseline."""
    changed_sku = state.get("inventory_sku") != sku
    if changed_sku:
        reset_parameters(state, parameters)
        state["inventory_sku"] = sku
    if state.get("inventory_context") != context:
        state.pop("baseline", None)
        state["inventory_context"] = context
    return changed_sku


def changed_parameters(a, b):
    return {
        key: (value, asdict(b)[key]) for key, value in asdict(a).items() if value != asdict(b)[key]
    }
