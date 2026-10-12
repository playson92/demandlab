# Historical study reproduction

The frontend displays an existing frozen study. Its presentation source has
changed; its data, model calculations, SQL, configurations and published study
artifacts are protected by [study_integrity.json](study_integrity.json). Check
them with `python scripts/protect_study.py check --manifest docs/study_integrity.json`.
Ordinary demo startup needs no Git, research dependencies, MLflow, raw source
workbook or local training artifacts. See the [demo instructions](../README.md).

The historical study uses 80 products and the default `weekday_mean_4w`, selected
on validation. The final issue date is 2011-11-10; the 28-day test ends 2011-12-08.
The verified delivery source is
`68277b676027369b815f76baea20ff057fcfb470`, which retains the reviewed study and
its post-test presentation-correction disclosure. Original training source and
content identities remain in the frozen manifests and execution records.
See [the correction disclosure](post_test_correction.md); replaying already
exposed labels is reproduction, not another independent final test.

The code identity used by the study includes `app/`. Therefore **do not run
`final_test`, `freeze`, `reproduce` or `record_ui_correction.py` on the new frontend
checkout**. The freeze guard is deliberately preserved. Install research tools
and replay the historical study only in a separate checkout at the verified
source, leaving the current demo untouched.

Requirements for research: Git, Python 3.12, uv, internet for the first locked
installation and the UCI source download (or the original local source workbook).
Choose a new empty directory for the following separate clone:

```sh
git clone https://github.com/playson92/demandlab.git demandlab-study
cd demandlab-study
git checkout --detach 68277b676027369b815f76baea20ff057fcfb470
uv sync --frozen --extra dev --python 3.12
uv run --no-sync python -m demandlab reproduce
```

At this historical commit all scientific dependencies are still base
dependencies; its `dev` extra matches the original checks. The new frontend
branch's equivalent development setup uses `--extra research --extra dev`, but
must not be used to rerun this study. To use a saved workbook in the historical
checkout, pass `--source-file "/path/to/online_retail_II.xlsx"` to `reproduce`.
Keep outputs, raw data, model files and MLflow databases in that separate clone.
Do not copy regenerated outputs over this frontend's protected reports/demo.

Historical CLI stages are download, prepare, validate, calibrate, freeze, test,
demo and report. Existing frozen reproduction skips validation/calibration.
Original test artifacts, including `*_original.*` and `test_execution.json`, are
retained. Numerical identity and original evaluation remain reviewable even as
the frontend evolves. Native and Docker demo checks test presentation and fixture
regressions only; frontend CI never downloads UCI or retrains the study.
