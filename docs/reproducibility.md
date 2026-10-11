# Reproducibility

Python 3.12, one resolver-generated cross-platform uv.lock; native PowerShell 5.1 scripts check native exit codes.

```powershell
Set-Location C:\projekty\demandlab
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1
# Separate process: full original-source study
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1
# Or -SourceFile C:\data\online_retail_II.xlsx
```

CLI: `python -m demandlab --help`; ordered stages download, prepare, validate, calibrate, freeze, test, demo, report. Existing frozen study skips validation/calibration in reproduce. To retrain from scratch use a separate checkout with the committed reviewed recipe and remove no original evidence.

Measured forecast-stage wall time: 542.7 seconds across 29 runs (includes feature generation/model fits; excludes ingestion). Per-run wall/CPU/RSS are in reports/resources.json.

Training source commit: `d9334f527bbd7bbca1b12a39626032dd97f91253`; working-tree content hash: `2f07c9e5c56a215405c529310ab130447057b5bcc86d53ab172919e186c28b88`. Delivery commit is recorded only in the external review bundle after the final commit.

MLflow logs locally to output/mlflow/tracking.sqlite and output/mlflow/artifacts without an HTTP server. run_mlflow.ps1 starts a loopback-only UI on port 5000. Raw/interim/processed, models, SQLite and .venv stay outside Git. Demo needs only committed daily/forecast Parquet, product CSV and versioned manifest. No widget downloads or trains.
