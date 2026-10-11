# Presentation correction after the original final test

Browser inspection found that the quality table labeled the signed percentage
bias as units. The metric has always been `100 * sum(prediction-y) / sum(abs(y))`;
only its UI label changed from units to percent.

The original evaluation was frozen and scored before this issue was found.
Original freeze, forecast manifest and metrics are retained as
`reports/*_original.*`; the original `test_execution.json` is also retained.
`scripts/record_ui_correction.py` verifies every numerical source/SQL/configuration
file against the original training commit and requires exactly this UI text change.
Forecasts, selected method, features, parameters, calibration and original results
are unchanged. Subsequent scoring is explicitly a replay with exposed test labels,
not a new independent test. Current freeze records both original forecasting code
and the corrected checkout identity for reproducibility.
