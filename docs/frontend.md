# Frontend design and extension guide

DemandLab presents the existing frozen study in three Polish analytical views:
product and forecast, inventory scenarios, and methods and results. The first
view starts with the validation-selected method and one matching uncertainty
band. Comparing methods is an explicit action. History defaults to 28 days,
with 84 and 180 day alternatives; chart zoom keeps the full data accessible.
The product's complete name lives in the main content, not the narrow sidebar.

The supported Streamlit theme uses warm `#F5F3ED`, white data surfaces, graphite
text and a dark green interaction accent. Arial and system sans-serif fallbacks
work offline and support Polish characters. Native controls provide keyboard
focus and accessible labels. Chart series use both named legends and differing
line styles; inventory events use both labels and bar patterns. No private DOM
selectors, generated CSS classes, external fonts or decorative images are used.

## Code structure

- `app/streamlit_app.py`: loading, shared product/method controls, navigation,
  validated URL state and provenance details.
- `app/artifacts.py`: validates the bundled frozen artifact contract. Incomplete
  SKU/method groups, mismatched origins and missing actual dates are errors.
- `app/presentation.py`: one method identifier → Polish label → color/style map,
  group labels and display formatting.
- `app/charts.py`: shared Plotly configuration and forecast/inventory figures.
- `app/state.py`: explicit SKU reset, example parameters and A/B context helpers.
- `app/views.py`: presentation of the three views, CSV/JSON export and calls to
  the unchanged `demandlab.inventory.simulate()` engine.

The presentation reads `data/demo/` and, for additional frozen detail, the
existing `reports/metrics_by_sku.csv` and `reports/metrics_by_horizon.csv`.
It does not import training, feature construction, evaluation, download or
MLflow modules. The validation view never shows final-test detail. Where the
bundled validation lacks product-level aggregate results, the UI explains the
available global level instead of calculating new results.

## State and scenarios

The shared `sku` and `method` controls persist between views. URLs use validated
stable identifiers, for example
`?view=inventory&sku=85123A&method=weekday_mean_4w`, with graceful fallback for
unknown values. Public query-parameter synchronization is explicit because
Streamlit's native binding serializes the formatted product/method names rather
than the stable identifiers required by this application. Copying a local URL
requires a running local app; it is not a public hosted demo.

Changing SKU explicitly resets its example stock and all parameters. Changing
lead time alone leaves stock untouched. The reset button restores the example
for the current product. A stores the parameters, full simulation result and
context. B is the current scenario. The UI shows parameter changes, both
summaries and differences; method, product, origin or scenario-path changes clear
A. Historical and hypothetical modes share one sales path between methods.
CSV/JSON exports describe the visible B, including parameters and provenance.
All costs are hypothetical; the comparison claims no business optimization.

## Extending and verifying

Add labels/styles centrally in `presentation.py`, not in individual views.
Keep domain calculations in the established Python engine and use saved reports
for model metrics. Additional artifacts require explicit integrity checks in the
loader, not inner joins that can silently reduce samples. Use stable widget keys
and callbacks to change state before controls are instantiated.

`tests/test_app.py`, `tests/test_demo.py`, `tests/test_frontend_state.py` and
`tests/test_presentation_regression.py` cover real widgets, frozen-data loading,
method styles, SKU resets, URL refresh, A/B context and direct equivalence to
the existing simulator. Browser evidence and delivery checks are recorded
separately under `output/`; selected screenshots are published in documentation.

The study identity remains in the frozen manifests, including the previous
post-test UI correction disclosure. The presentation is versioned by its current
Git commit; changing app code does not reapprove or rerun the frozen final test.
This implementation was developed with AI assistance, without claims of
independent sole authorship or commercial outcomes.

Inventory metrics use two explicit rows, with responsive columns. The chart
reserves a bottom margin for its wrapping legend, separate from both subplot
titles and the date axis. Tables retain all metrics and advertise horizontal
scrolling. Shared presentation helpers format Polish decimals, integer stock,
two-decimal errors/costs and percentage-point deltas; input arrays and raw exports
retain their original precision.

Browser evidence distinguishes interactions, rendered SVG measurements and a
human review of screenshots. `scripts/capture_evidence.py` saves the requested
viewport before taking a separate full-content image; the latter increases
height and is not evidence of the original viewport. Inventory checks compare
the actual legend/title rectangles and SVG boundaries, including in CI smoke
runs. A full local run also uses Chromium's native 200% tab zoom and records the
actual viewport and pixel ratio, with separate captures of both ends of the
inventory chart. Automated results leave visual review as `NOT_RUN` until the
saved images have been inspected.

For a final committed delivery, keep current local evidence in one directory
under `output/codex_runs/`, including `delivery_checks.json` with the final SHA.
Pass the selected evidence directory as `--evidence-dir` and the current run
directory as `--destination` to `scripts/build_review_bundle.py`. This includes only explicitly selected current
evidence, exact committed source and a SHA-256 inventory, without older trial
logs, browser profiles or extracted demo environments.
