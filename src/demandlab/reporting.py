"""Generate human-readable reports from actual experiment artifacts."""

from pathlib import Path

import pandas as pd

from demandlab.pipeline import load


def markdown_table(frame: pd.DataFrame) -> str:
    def cell(value):
        if pd.isna(value):
            return "N/A"
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    rows = [
        "| " + " | ".join(frame.columns) + " |",
        "| " + " | ".join(["---"] * len(frame.columns)) + " |",
    ]
    rows += [
        "| " + " | ".join(cell(v) for v in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join(rows)


def generate_report(root: Path):
    scores = pd.read_csv(root / "reports/metrics.csv")
    selection = load(root / "reports/model_selection.json")
    frozen = load(root / "reports/freeze_manifest.json")
    products = pd.read_csv(root / "reports/product_selection.csv", dtype={"sku": str})
    columns = ["split", "method", "mae", "wape", "coverage80", "width80", "coverage95", "width95"]
    table = markdown_table(scores[columns])
    errors = pd.read_csv(root / "data/demo/metrics_by_sku.csv", dtype={"sku": str})
    worst = errors[errors.method == selection["winner"]].nlargest(5, "mae")
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "results.md").write_text(
        "# Results\n\nRecorded sales, not unconstrained demand. All methods use the same 80 selected SKUs and 28-day windows.\n\n"
        + table
        + "\n\nCoverage is a fraction, interval width is units. Validation intervals are N/A because later calibration was unavailable then.\n\n"
        + f"Default method: **{selection['winner']}**, chosen on pooled four-window validation WAPE, with the prespecified 1% simplicity rule. Final test does not change the recipe.\n\n"
        + "## Hard cases\n\nLargest final-test MAE cases for the frozen winner (diagnostic only, not product selection):\n\n"
        + markdown_table(worst[["sku", "mae", "wape", "bias"]])
        + "\n\nLarge valid transactions, product disappearance and intermittent sales are retained. Zero-filled dates rely on source completeness, which cannot be independently established.\n",
        encoding="utf-8",
    )
    (docs / "model_card.md").write_text(
        "# Model card\n\n"
        f"Purpose: compare daily recorded-sales forecasts for UK UCI II portfolio data. Frozen default: {selection['winner']}.\n\n"
        + table
        + "\n\nOne global direct Poisson HistGradientBoostingRegressor with categorical SKU is compared with two baselines. SKU selection and names use initial history only. Training origins end at least 28 days before cutoff.\n\n"
        + "Empirical 80%/95% nominal intervals use signed scaled residuals from two calibration origins. Temporal/product dependence and distribution shift prevent a per-SKU coverage guarantee. Point forecasts estimate the mean; they need not lie inside signed empirical intervals.\n\n"
        + "Not for current trading, replenishment optimization or business ROI. Dataset ends in 2011. No actual inventory, latent demand, stockouts or procurement costs are observed. There is no customer-level model and no customer identifiers are published.\n",
        encoding="utf-8",
    )
    resources = load(root / "reports/resources.json")
    total = sum(v["elapsed_seconds"] for v in resources.values())
    (docs / "reproducibility.md").write_text(
        "# Reproducibility\n\nPython 3.12, one resolver-generated cross-platform uv.lock; native PowerShell 5.1 scripts check native exit codes.\n\n"
        "```powershell\nSet-Location C:\\projekty\\demandlab\npowershell -ExecutionPolicy Bypass -File scripts\\bootstrap.ps1\npowershell -ExecutionPolicy Bypass -File scripts\\verify.ps1\npowershell -ExecutionPolicy Bypass -File scripts\\run_app.ps1\n# Separate process: full original-source study\npowershell -ExecutionPolicy Bypass -File scripts\\reproduce.ps1\n# Or -SourceFile C:\\data\\online_retail_II.xlsx\n```\n\n"
        "CLI: `python -m demandlab --help`; ordered stages download, prepare, validate, calibrate, freeze, test, demo, report. Existing frozen study skips validation/calibration in reproduce. To retrain from scratch use a separate checkout with the committed reviewed recipe and remove no original evidence.\n\n"
        + f"Measured forecast-stage wall time: {total:.1f} seconds across {len(resources)} runs (includes feature generation/model fits; excludes ingestion). Per-run wall/CPU/RSS are in reports/resources.json.\n\n"
        + f"Training source commit: `{frozen['code']['source_sha']}`; working-tree content hash: `{frozen['code']['working_tree_sha256']}`. Delivery commit is recorded only in the external review bundle after the final commit.\n\n"
        + "MLflow logs locally to output/mlflow/tracking.sqlite and output/mlflow/artifacts without an HTTP server. run_mlflow.ps1 starts a loopback-only UI on port 5000. Raw/interim/processed, models, SQLite and .venv stay outside Git. Demo needs only committed daily/forecast Parquet, product CSV and versioned manifest. No widget downloads or trains.\n",
        encoding="utf-8",
    )
    (docs / "portfolio_case_study.md").write_text(
        "# Portfolio case study\n\nThe question is whether a more complex forecast improves a simple weekly reference, and how a fixed forecast affects a hypothetical stock policy.\n\n"
        + f"Built from original UCI Online Retail II, {len(products)} selected UK SKUs. Selected winner: {selection['winner']}.\n\n"
        + "Three choices make the comparison credible: SKU selection before validation; direct origin-anchored features with fully observed training labels; separate model-selection, calibration and final-test windows. The test forecast is saved before label joining.\n\n"
        + "AI generated and integrated code, tests, UI and documentation. Automated checks, independent agent review, real source reconciliation and actual browser inspection provide evidence; this is not independently authored human analysis or commercial deployment.\n\n"
        + "Observed environment issue: sandbox GitHub auth appeared invalid and MLflow import raised an EvaluationDataset ImportError; authorized execution outside sandbox succeeded. GitHub CLI also rejected sandbox-owned Git directories; a process-local safe.directory exception fixed access without global configuration changes.\n\n"
        + "No claimed revenue uplift, saved procurement cost or optimal stock policy. Costs are explicit hypothetical inputs.\n",
        encoding="utf-8",
    )
    (docs / "demo_script.md").write_text(
        "# Three-minute demo\n\n1. Overview (30s): explain recorded sales, UK, 80 products, dates 2009â€“2011, frozen default selected by validation. Use the regular/intermittent examples chosen from initial units only.\n"
        "2. Forecast (45s): show origin, four-week forecasts, actuals and signed empirical nominal intervals. Toggle methods without training.\n"
        "3. Quality (45s): separate validation selection from final test. Show common dates, horizon errors and difficult SKU. Do not tune after seeing test.\n"
        "4. Inventory (60s): same actual scenario for all methods; hold initial stock constant while changing lead time. Explain units, finite horizon, lost sales and hypothetical costs. Export CSV/JSON with provenance.\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# DemandLab\n\nA reproducible forecasting portfolio connecting **recorded sales** to a transparent hypothetical inventory policy. For recruiters and data science teams: original-source reconciliation, leakage controls, honest baselines and a usable Polish Streamlit demo.\n\n"
        "![Forecast](docs/screenshots/forecast.png)\n![Model quality](docs/screenshots/quality.png)\n![Inventory simulator](docs/screenshots/simulator.png)\n\n"
        "## Run on Windows\n\n```powershell\nSet-Location C:\\projekty\\demandlab\npowershell -ExecutionPolicy Bypass -File scripts\\bootstrap.ps1\npowershell -ExecutionPolicy Bypass -File scripts\\run_app.ps1\n```\n\nOpen http://localhost:8501. Demo uses committed real aggregates; it requires no UCI download or training. Package installation requires network.\n\n"
        "```powershell\npowershell -ExecutionPolicy Bypass -File scripts\\verify.ps1\npowershell -ExecutionPolicy Bypass -File scripts\\reproduce.ps1\n# Optional local original workbook:\n# powershell -ExecutionPolicy Bypass -File scripts\\reproduce.ps1 -SourceFile C:\\data\\online_retail_II.xlsx\n```\n\n"
        "## Docker\n\n```text\ndocker compose up --build\n```\n\nSame bundled demo at localhost:8501; source download and model fitting never run at startup.\n\n"
        "## Actual results\n\n"
        + table
        + "\n\n"
        + f"Default: **{selection['winner']}**, selected on pooled validation WAPE before calibration and test. Coverage is a fraction; widths are recorded units.\n\n"
        + "## Architecture and decisions\n\n```mermaid\nflowchart LR\n  UCI[Original UCI II XLSX] --> SQL[DuckDB cleaning and reconciliation]\n  SQL --> P[Daily Parquet and initial SKU selection]\n  P --> V[Four validation origins]\n  V --> C[Two calibration origins]\n  C --> F[Frozen recipe and saved test forecasts]\n  F --> T[Final evaluation]\n  T --> D[Real demo artifacts]\n  D --> UI[Streamlit and inventory simulator]\n```\n\n"
        "Origins anchor every historical feature. Training labels must satisfy origin+28<=cutoff. Initial 365-day SKU selection avoids future survival bias. Signed calibration intervals are applied only after both calibration windows.\n\n"
        "## Limits and evidence\n\nHistorical 2009â€“2011 data does not forecast current trading. Zero-filled dates assume source completeness; source contains no real stock, unmet demand or supply lead times. Large valid transactions are retained. Inventory costs and safety stock are hypothetical; finite-horizon truncation is explicit.\n\n"
        "See [data contract](docs/data_contract.md), [methodology](docs/methodology.md), [results](docs/results.md), [model card](docs/model_card.md), [simulator](docs/inventory_simulator.md), [reproduction](docs/reproducibility.md), [case study](docs/portfolio_case_study.md), [demo script](docs/demo_script.md) and [execution evidence](PROJECT_STATE.md).\n\n"
        "Own code: MIT. Derived UCI data: CC BY 4.0, Chen (2012), DOI [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D); see DATA_LICENSE.md. Raw invoices/customer IDs are not distributed.\n\n"
        "## Po polsku\n\nDemandLab porĂłwnuje prognozy zarejestrowanej sprzedaĹĽy i pokazuje ich dziaĹ‚anie w hipotetycznej polityce zapasu. Cztery widoki aplikacji: przeglÄ…d, prognoza produktu, jakoĹ›Ä‡ modeli, symulator z eksportem. Wynik testu nie sĹ‚uĹĽy do wyboru metody.\n",
        encoding="utf-8",
    )
