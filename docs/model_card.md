# Model card

Purpose: compare daily recorded-sales forecasts for UK UCI II portfolio data. Frozen default: weekday_mean_4w.

| split | method | mae | wape | coverage80 | width80 | coverage95 | width95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| validation | hist_gradient_boosting | 32.760 | 123.365 | N/A | N/A | N/A | N/A |
| validation | seasonal_naive_7 | 36.694 | 138.180 | N/A | N/A | N/A | N/A |
| validation | weekday_mean_4w | 32.592 | 122.731 | N/A | N/A | N/A | N/A |
| final_test | hist_gradient_boosting | 36.705 | 93.660 | 0.796 | 63.922 | 0.952 | 242.280 |
| final_test | seasonal_naive_7 | 43.669 | 111.430 | 0.796 | 85.665 | 0.955 | 291.493 |
| final_test | weekday_mean_4w | 39.129 | 99.846 | 0.790 | 82.862 | 0.958 | 276.707 |

One global direct Poisson HistGradientBoostingRegressor with categorical SKU is compared with two baselines. SKU selection and names use initial history only. Training origins end at least 28 days before cutoff.

Empirical 80%/95% nominal intervals use signed scaled residuals from two calibration origins. Temporal/product dependence and distribution shift prevent a per-SKU coverage guarantee. Point forecasts estimate the mean; they need not lie inside signed empirical intervals.

Not for current trading, replenishment optimization or business ROI. Dataset ends in 2011. No actual inventory, latent demand, stockouts or procurement costs are observed. There is no customer-level model and no customer identifiers are published.
