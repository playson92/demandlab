# Project state

## Execution plan 00–05
00 environment / bootstrap / official source / vertical slice.
01 full ingestion, disjoint exclusions, initial-only selection, reconciliation.
02 frozen windows, direct features, baselines, metrics, leakage tests.
03 four validation origins, three predefined tree configurations, two calibration origins.
04 UI, inventory, exports, tests, Docker/CI, independent methodology review.
05 freeze, saved test forecasts then labels, reports/demo/screenshots, clean checkout, PR/CI/bundle.

## Evidence and current work
- PASS: native Windows PowerShell 5.1, C: workspace accessible.
- PASS: Python 3.12.10 available by absolute executable path; Git 2.52.
- PASS: elevated GitHub check identifies playson92, User; repo lookup returned HTTP 404.
- PASS: elevated Docker daemon responds 29.8.1.
- PASS: inspected portfolio-project-template README and pyproject; no applicable parent AGENTS.md found.
- PASS: bootstrap commit on main 9a16b22.
- Initial sandbox GitHub/Python/Docker failures were access restrictions; elevated checks succeeded.
- GitHub creation first attempt failed because elevated execution did not preserve cwd; retried with explicit Set-Location.
- PASS 00: public repository https://github.com/playson92/demandlab; main bootstrap; implementation on feat/demandlab-mvp; resolver-generated uv.lock and .venv; real official source downloaded.
- PASS 01: both sheets 1,067,371 source rows; source 2009-12-01..2011-12-09; D=2011-12-08. Selection 2010-11-30 uses initial history only: 40 intermittent + 40 regular.
- PASS: selected same-scope SQL line_units=daily_units=2,062,484, 82,451 accepted lines. reports/reconciliation.json and source manifest hold evidence.
- PASS 02: seven concrete nonoverlapping 28-day windows, direct origin-only features, baselines, manual metrics and leakage tests implemented. Model/evaluation/inventory review: reports/methodology_review.md.
- PASS: six ingestion tests, twelve model/evaluation tests, fifteen inventory/AppTest tests (separate module runs; integrated verification pending).
- PASS: native scripts/bootstrap.ps1 installed/checks locked dependencies locally; no global Python/Git configuration changed.
- PASS validation: four origins, three prespecified tree recipes and two baselines trained on actual UCI. Pooled WAPE: seasonal naive 138.1802%, weekday mean 122.7310%, best tree B 123.3650%. Default weekday_mean_4w chosen before calibration/test.
- Source implementation commit: 1705d7b; provenance includes uncommitted content hash. Provenance and resume safeguards were strengthened during validation; numeric feature/model recipes stayed unchanged.
- Engineering findings fixed before test: initial_units demo field mismatch; synthetic MLflow update experiment mismatch; interrupted-freeze resume and integrity guards; simulator hand-test expected order; nonstandard NaN in JSON export.
- PASS: scripts/verify.ps1: Ruff check/format; 34 integrated tests including full isolated synthetic pipeline + exact replay + MLflow + AppTest, 144.72s. output/verify-pretest.log and output/junit.xml. Warnings: upstream SQLAlchemy deprecation and sandbox cache ownership; cache disabled for later script runs.
- PASS 03: four validation origins complete; recipe winner weekday_mean_4w / tree B. Both calibration origins complete for three methods; 1,120 residuals per method/horizon bucket; linear empirical quantiles; no test labels used.
- PASS: targeted current pipeline/replay test after detailed-report integration: 1 passed, 127.81s, output/pipeline-current.log/.xml. Upstream SQLAlchemy deprecation warning only.
- PASS: local MLflow HTTP 200 on 127.0.0.1 using same SQLite store; own processes stopped. UI helper reduced to one worker for laptop use.
- IN_PROGRESS 04: UI/simulator/scripts/Docker/CI implemented; actual browser and image verification pending real demo.
- PASS 05 original study: source commit d9334f5, clean code, original freeze then saved final forecasts then test labels. Original final WAPE: tree 93.6596%, seasonal naive 111.4303%, weekday mean 99.8456%; default remains validation winner weekday_mean_4w.
- PASS: real aggregates/forecasts packaged in data/demo, no raw data/model/MLflow needed; practical docs, detailed fold/SKU/regularity/horizon reports generated.
- PASS: 35 final integrated tests, 158.29s, output/verify-final.log + JUnit; includes real UCI demo AppTest four views. Upstream SQLAlchemy deprecation warning only.
- PASS: actual Docker build, start and HTTP 200 'ok' on 8519; container healthy, image sha256:727639bcca6cead502662545443750b88f446c9fb70703c1ae0dd06343259318. Logs output/docker-build.log. Build's Git metadata access warning does not affect image; version is separately recorded.
- PASS: native app through run_app.ps1 on 8517. Existing ports 8501/8502 were occupied and not terminated. Browser screenshots forecast/quality/simulator and actual CSV/JSON downloads; inspected desktop 1440x1150 and smaller 768x1024; no JavaScript errors. reports/browser_check.json.
- Post-test presentation finding: quality table incorrectly labeled percentage bias as units. Only label changed. docs/post_test_correction.md and scripts/record_ui_correction.py verify numerical code unchanged, retain *_original manifests/metrics and original execution evidence, explicitly mark later scoring as replay with exposed labels. No numerical recipe/outcome changes.
- Browser automation initially failed on port conflict, a virtualized SKU menu, strict duplicate text and an interrupted disabled widget. Selector/port fixes resolved these; actual screenshots were captured after successful checks.
- IN_PROGRESS: clean checkout startup, reproduce.ps1 actual source replay, full branch push/PR/current CI and review bundle.
- Next: complete delivery verification, preserve exact delivery SHA outside tracked files.
