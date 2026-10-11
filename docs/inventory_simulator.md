# Inventory simulator

The simulator compares fixed 28-day forecasts on one shared sales scenario. Recorded UCI sales are not unconstrained demand and do not reconstruct the historical warehouse. All monetary inputs are hypothetical GBP assumptions; purchase costs, margins, ROI, savings and salvage value are excluded.

For day `d` (one-based), receive deliveries, review and order if scheduled, serve scenario sales, record lost units and end-of-day costs. Review days are `1, 1+R, ...`; an order arrives in the morning of `d+L`, never on its order day. Initial pipeline is zero; unmet units are lost without backorders.

On a review day:

```
IP = available stock + outstanding units
S = ceil(sum(forecast[d : min(28, d+L+R-1)]) + B)
Q = max(0, S - IP), provided d+L <= 28
```

The range above includes both endpoints. Forecasts are nonnegative, stock and orders use integer units. `L` is 1–21 calendar days, `R` is 1–7, `L+R <= 28`, and `B` is an explicit nonnegative buffer in units, without a guaranteed service level. The target window is truncated at day 28. No unknown future forecasts are appended and no order arriving after day 28 is placed. Ending stock and pipeline are explicitly reported, without a salvage valuation. This finite-horizon policy is not an optimal continuous replenishment policy.

`order_decision` receives only an immutable forecast tuple, day, current stock, outstanding units and parameters. Today's and future sales are passed separately to `simulate`, after the order decision. Past realized sales may affect the current available stock. Unit tests alter future sales and costs independently to protect these information boundaries.

Historical mode uses the recorded next 28 days identically for all methods. Hypothetical mode uses the validation winner's forecast multiplied by an explicit common factor and rounds with `floor(x+0.5)`. This scenario is not an independent forecast evaluation or a promise of future sales. Changing costs recalculates the same physical policy; changing lead time does not automatically change initial stock. The default initial stock is `ceil(7 * mean(last 28 known days))`.

Holding costs apply to ending units × GBP/unit/day; order costs apply once per positive order; shortage costs apply to unserved units × GBP/unit. Service rate is served units / scenario sales, or null for zero sales. A zero-stock day with full service is not a shortage day. The inventory identity is `ending stock + cumulative served = initial stock + cumulative receipts`.

`simulate(forecast, sales, InventoryParameters(...))` returns `SimulationResult`, with `.daily`, `.summary`, `.export_csv(provenance)` and `.export_json(provenance)`. CSV repeats parameters, scenario rule and provenance on every daily row. JSON includes parameters, fixed forecast, complete scenario path, daily event balances, summary and limitations. Supply SKU, origin, method, run ID and source hash in provenance. Daily nominal forecast bounds are not summed or described as lead-time service guarantees.
