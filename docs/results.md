# Results

Recorded sales, not unconstrained demand. All methods use the same 80 selected SKUs and 28-day windows.

| split | method | mae | wape | coverage80 | width80 | coverage95 | width95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| validation | hist_gradient_boosting | 32.760 | 123.365 | N/A | N/A | N/A | N/A |
| validation | seasonal_naive_7 | 36.694 | 138.180 | N/A | N/A | N/A | N/A |
| validation | weekday_mean_4w | 32.592 | 122.731 | N/A | N/A | N/A | N/A |
| final_test | hist_gradient_boosting | 36.705 | 93.660 | 0.796 | 63.922 | 0.952 | 242.280 |
| final_test | seasonal_naive_7 | 43.669 | 111.430 | 0.796 | 85.665 | 0.955 | 291.493 |
| final_test | weekday_mean_4w | 39.129 | 99.846 | 0.790 | 82.862 | 0.958 | 276.707 |

Coverage is a fraction, interval width is units. Validation intervals are N/A because later calibration was unavailable then.

Default method: **weekday_mean_4w**, chosen on pooled four-window validation WAPE, with the prespecified 1% simplicity rule. Final test does not change the recipe.

The tree's original test WAPE is lower by 6.20 percentage points than the frozen
default. This observation does not change the winner or any recipe. Bias in
detailed reports is signed percentage overprediction, not units. A UI unit-label
correction after the original assessment is documented in
[post_test_correction.md](post_test_correction.md); original manifests/metrics
are retained and later scoring is explicitly a replay with exposed labels.

## Hard cases

Largest final-test MAE cases for the frozen winner (diagnostic only, not product selection):

| sku | mae | wape | bias |
| --- | --- | --- | --- |
| 22197 | 330.179 | 68.264 | -39.969 |
| 84077 | 218.250 | 164.628 | 120.744 |
| 21915 | 171.643 | 320.187 | 168.088 |
| 16014 | 127.804 | 681.619 | 483.048 |
| 20668 | 126.929 | 84.922 | -16.201 |

Large valid transactions, product disappearance and intermittent sales are retained. Zero-filled dates rely on source completeness, which cannot be independently established.
