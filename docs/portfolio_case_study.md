# Portfolio case study

The question is whether a more complex forecast improves a simple weekly reference, and how a fixed forecast affects a hypothetical stock policy.

Built from original UCI Online Retail II, 80 selected UK SKUs. Selected winner: weekday_mean_4w.

Three choices make the comparison credible: SKU selection before validation; direct origin-anchored features with fully observed training labels; separate model-selection, calibration and final-test windows. The test forecast is saved before label joining.

AI generated and integrated code, tests, UI and documentation. Automated checks, independent agent review, real source reconciliation and actual browser inspection provide evidence; this is not independently authored human analysis or commercial deployment.

Observed environment issue: sandbox GitHub auth appeared invalid and MLflow import raised an EvaluationDataset ImportError; authorized execution outside sandbox succeeded. GitHub CLI also rejected sandbox-owned Git directories; a process-local safe.directory exception fixed access without global configuration changes.

No claimed revenue uplift, saved procurement cost or optimal stock policy. Costs are explicit hypothetical inputs.

Browser inspection found an actual presentation error: percentage bias was
labeled as units. Only the label changed; a script verified numerical code
against the original commit and retained original test evidence. See
[post-test correction](post_test_correction.md). Browser automation also needed
to filter the virtualized SKU list and scope navigation to the sidebar; these
were test-selector fixes. Occupied local ports were avoided without terminating
any existing user process.
