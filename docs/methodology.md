# Methodology

DemandLab forecasts **daily recorded sales units**, rather than uncensored demand.
The original UCI Online Retail II final transaction date is excluded in advance as
potentially incomplete. Missing internal calendar days are treated as zero recorded
sales under an explicit completeness assumption; no zeros precede a product's
first recorded sale. Sales can be censored by availability that the source does not
record. All large valid sales remain in the target.

## Selection and temporal protocol

Product selection uses only the initial 365 admitted calendar days. Candidates
have at least 180 available days and 20 positive days. Forty products with positive
day share below 40%, and forty at or above 40%, are selected by descending recorded
units and ascending SKU for ties. Any unavailable places are filled from the other
group. Product descriptions and regularity are frozen from this initial history;
products remain even when sales later disappear. The selection artifact stores the
actual cutoff and statistics. Selection finishes before the first validation.

Relative to admitted end date D, the four validation windows are D-195..D-168,
D-167..D-140, D-139..D-112 and D-111..D-84. Calibration uses D-83..D-56 and
D-55..D-28. The final test is D-27..D. Dates are inclusive and each origin is the
end of the preceding day. Generated manifests record the concrete dates.

The downloaded workbook contains 1,067,371 rows across `Year 2009-2010` and
`Year 2010-2011`, with local dates 2009-12-01 through 2011-12-09. Therefore
D is 2011-12-08 and initial selection ends 2010-11-30. The actual frozen dates are:

| Split | Origin | Inclusive evaluation dates |
|---|---|---|
| validation_1 | 2011-05-26 | 2011-05-27 through 2011-06-23 |
| validation_2 | 2011-06-23 | 2011-06-24 through 2011-07-21 |
| validation_3 | 2011-07-21 | 2011-07-22 through 2011-08-18 |
| validation_4 | 2011-08-18 | 2011-08-19 through 2011-09-15 |
| calibration_1 | 2011-09-15 | 2011-09-16 through 2011-10-13 |
| calibration_2 | 2011-10-13 | 2011-10-14 through 2011-11-10 |
| final_test | 2011-11-10 | 2011-11-11 through 2011-12-08 |

Each origin issues all 28 horizons together. Training expands through the origin.
Training examples use weekly origins on a grid aligned to the evaluated origin,
and **training origin + 28 <= current cutoff**. Thus all labels of every training
origin are observed. No random temporal split or within-window updates are used.
Products need 56 known calendar days before their first feature row.

## Models and features

`seasonal_naive_7` repeats the final known week four times. `weekday_mean_4w`
uses the last four known occurrences of the forecast weekday. Both stay fixed
throughout the horizon, including horizons 8 and 20.

One global direct `HistGradientBoostingRegressor` shares products and horizons.
Historical features are y[o], y[o-1], y[o-6], y[o-13], y[o-27], mean, population
standard deviation and zero share over 7/28/56 days ending at o, days since the
last positive sale, and the mean of the relevant weekday over the last 28 days.
Known future calendar features are horizon, weekday and month. SKU categories are
mapped exclusively from eligible training rows; categorical SKU is explicitly
flagged in the model's numeric matrix. An unseen category is represented as missing.
Numeric matrices use float32. The model uses Poisson loss, disabled early stopping,
seed 42 and at most two numerical threads. All-zero training labels produce zeros.

The three predetermined configurations are:

| Config | learning rate | iterations | leaves | minimum leaf samples | L2 |
|---|---:|---:|---:|---:|---:|
| A | 0.05 | 150 | 15 | 30 | 1 |
| B | 0.05 | 200 | 31 | 30 | 1 |
| C | 0.08 | 150 | 15 | 60 | 5 |

Tree configuration is selected using pooled absolute errors and actual units
across four validation windows. Global method selection uses that pooled WAPE.
When the best method improves a simpler candidate by less than 1% of the simpler
candidate's WAPE, retain the simplest eligible method: seasonal naive, weekday
mean, then tree. Within the tree family equal scores use alphabetical config order.
When the minimum WAPE is zero, select the simplest zero-error candidate. If all
WAPE values are undefined, selection fails explicitly instead of inventing a winner.

## Empirical uncertainty

Calibration uses signed residuals `(y-prediction)/scale`, where scale is
`max(1, mean of final 28 known days at origin)`. For each method separately,
horizons are grouped 1–7, 8–14, 15–21 and 22–28. Quantiles 0.025, 0.10, 0.90,
0.975 use NumPy's `linear` interpolation. A bucket with fewer than 100 rows falls
back to all calibration residuals for that method. The artifact retains bucket
count, effective count and fallback source. Both calibration windows are required;
validation and test labels are rejected.

Bounds are `max(0, prediction + quantile * scale)` and are checked for ordering
and nesting. The point forecast estimates the mean and need not lie at the middle
of the empirical bounds. Parameters apply only after the second calibration window
has completed; earlier forecast quantiles stay null and interval metrics stay N/A.
These are empirical intervals at nominal 80% and 95%, without per-product coverage
guarantees. Temporal and cross-product dependence, few origins and distribution
changes prevent treating individual calibration rows as independent experiments.

## Metrics and final test

MAE is the mean absolute error. Pooled WAPE is `100 sum(abs(y-p))/sum(abs(y))`;
signed bias is `100 sum(p-y)/sum(abs(y))`, with positive values indicating
overprediction. Zero denominators return null; there is no epsilon. Coverage is
an inclusive fraction, interval width is the mean upper minus lower bound, and
pinball loss is `mean(max(q*(y-bound), (q-1)*(y-bound)))` for each of four quantiles.
Global WAPE pools units and errors, rather than averaging product percentages.

The final test is evaluated only after independent leakage and inventory review,
the freeze manifest and saved predictions. The freeze identifies input hash,
selected SKUs, features, configuration, winner, calibration, seed, environment and
code. Test labels are joined after predictions are written. The test cannot change
model choice, thresholds or features. A genuine post-test bug correction must
preserve the old result and label subsequent evaluation as exposed-test correction.

Unit tests mutate all values after an origin, compare full and truncated inputs,
check all 28 training labels, and manually verify metrics and calibration. They
are synthetic correctness checks, not evidence of a successful full UCI experiment.

The implementation follows the installed scikit-learn histogram boosting API:
[HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).
