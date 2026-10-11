# Pre-final-test methodology and inventory review

Status: **APPROVED_FOR_FINAL_TEST**

Review date: 2026-10-11. Reviewer: delegated methodology agent. The reviewer
implemented features/model unit tests, then independently inspected the root
agent's pipeline/tracking and the application agent's inventory simulator.
This is an AI engineering review, not independent human statistical certification.
No real final-test outcomes or scores were examined or calculated during this review.

## Scope and checks

Reviewed `features.py`, `forecasting.py`, `evaluation.py`, `pipeline.py`,
`tracking.py`, `inventory.py`, their synthetic tests, and the saved source,
selection, reconciliation and date protocol metadata.

- PASS: source metadata identifies UCI Online Retail II 502, both year sheets,
  1,067,371 lines and source dates 2009-12-01 through 2011-12-09. The admitted
  end is 2011-12-08, with the final source date excluded before evaluation.
- PASS: selection cutoff 2010-11-30 precedes first validation 2011-05-27.
  Selected products and regularity are retained from the initial history.
- PASS: seven inclusive 28-day windows are disjoint; origins are the preceding
  day. Final test is 2011-11-11 through 2011-12-08, origin 2011-11-10.
- PASS: feature construction discards future rows before inspecting values.
  Lags and rolling statistics end at each origin; future features describe known
  calendar dates. All training origins satisfy origin+28 <= cutoff. Weekly
  alignment and all 28 observed labels are checked. SKU mapping is learned from
  training only and explicitly handled as categorical by histogram boosting.
- PASS: all 28 predictions are issued together. Baselines repeat the known week
  or use four known weekday observations even at horizons 8 and 20.
- PASS: winner selection pools validation absolute errors and actual units.
  The prescribed three tree recipes and simpler-method preference are frozen.
  Tree numeric matrices use float32, Poisson loss, seed 42, no automatic early
  stopping and at most two numerical threads.
- PASS: calibration accepts exactly calibration_1 and calibration_2, rejects
  test/validation labels and uses signed origin-scaled residuals. Quantiles use
  linear interpolation and the predetermined 100-row pooled-method fallback.
  Applying later calibration to earlier origins raises an error; earlier quantiles
  stay null. Bounds are nonnegative, ordered and nested.
- PASS: manually checked MAE, pooled WAPE, signed percentage bias, pinball,
  coverage and width. Zero denominators yield null without epsilon.
- PASS: predictions are written before labels are joined. The freeze precedes
  final issuance/scoring. Scoring verifies frozen predictions, freeze hash,
  modeling code/protocol, source, daily data, selection, recipe and calibration.
  Calibration cannot overwrite frozen parameters. Interrupted freeze retains
  unchanged inputs, completes missing forecasts and reissues pending runs;
  completed freeze verifies saved prediction bytes.
- PASS: SQLite tracking URI is derived from the local root on Windows/Linux.
  Synthetic experiments route to an explicitly separate experiment and temporary
  database during review. Actual test runs are updated only after scoring.
- PASS: inventory policy receives only the immutable forecast, current day,
  available state, pipeline and parameters. Actual future sales belong to the
  execution engine. Receipts occur before order decisions; orders arrive on d+L;
  sales follow decisions. The target window ends at day 28, with no delivery after
  the horizon, no backorders, integer units and end-of-day holding cost.
- PASS: inventory tests check conservation, L=1 timing, future-sales information
  boundary, cost-only invariance, zero sales, terminal horizon and real CSV/JSON.

## Findings resolved before final exposure

1. The simulator's manual test expected day-3 order 3, but receiving 2 units
   gives opening stock 2 and target 4, so order is 2. The policy was correct;
   the test expectation was corrected and rerun.
2. Demo selection referenced `units`, while the data contract stores
   `initial_units`. The demo was corrected to use initial-history units.
3. Updating a synthetic MLflow run initially selected the real-data experiment,
   causing an actual MLflow experiment-ID mismatch. Updates now pass the
   synthetic flag. An isolated SQLite rerun confirmed the fix.
4. Initial scoring checked predictions only. Freeze/data/code/recipe/calibration
   identity checks and guards against post-freeze calibration were added.
5. Interrupted freeze could leave a manifest without completed predictions.
   Resume now preserves unchanged freeze inputs, finishes forecasts and rejects
   incomplete pending tracking rows. Complete freeze checks prediction hash.

## Executed evidence and limits

`python -m pytest tests/test_forecasting.py tests/test_evaluation.py -q`:
**PASS**, 12 tests, 107.40 seconds in the filesystem sandbox (initial imports).

`python -m pytest tests/test_forecasting.py tests/test_evaluation.py
tests/test_inventory.py -q -p no:cacheprovider`:
**PASS**, 22 tests, 6.50 seconds in the approved native environment, after the
manual inventory fixture correction. No real final-test scoring was performed.

Ruff check and format check on the model/evaluation files and their tests:
**PASS**, all checks passed and five files already formatted.

An isolated temporary SQLite `record_run(synthetic=True)` followed by
`update_run(synthetic=True)`: **PASS**, process output
`SYNTHETIC_TRACKING_UPDATE_PASS`. The initial mismatch failure is preserved in
the engineering finding above rather than described as a successful check.

Full synthetic pipeline integration, application browser inspection, Docker,
full UCI experiment completion and CI are outside this review's executed evidence
and remain the coordinator's separate required checks. This approval authorizes
the methodology's final freeze and test only after those pretest implementation
checks complete; it makes no claim about eventual model accuracy or service levels.

## Follow-up: replay and portable checkout review

The replay additions were inspected before real final-test exposure, without
running additional tree training. Validation replay compares the reproduced
winner, tree recipe and candidate WAPE to the original (rtol/atol 1e-8), then
retains the original recipe. Calibration replay compares quantiles with the same
tolerance and retains the original calibration. It does not choose a new recipe
from published test outcomes. The CLI recreates missing local outputs in a fresh
checkout and freezes the original reviewed recipe before joining final labels.

Code identity normalizes CRLF to LF for source/configuration text, and selection
CSV identity does the same. The daily Parquet retains an exact byte identity;
a platform/library difference therefore fails visibly rather than quietly
changing the experiment. This static review does not claim a completed
cross-platform full-UCI replay.

The final scoring guards remain sufficient for source/processed-data/selection,
modeling-code/protocol, recipe, calibration and saved-forecast integrity. Both
completed freeze reuse and interrupted regeneration preserve the original freeze
manifest; scoring still verifies all input identities before joining labels.
The local bootstrap installs the resolved environment without changing global
Python configuration. A later reproduction must be described as a replay of the
original frozen test with previously published labels, preserving original
execution evidence; it is not a new independent test.
