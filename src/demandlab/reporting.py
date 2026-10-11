"""Publish frozen experiment artifacts without replacing editorial documentation."""

import json
from pathlib import Path

import pandas as pd


def markdown_table(frame: pd.DataFrame) -> str:
    def cell(value):
        if pd.isna(value):
            return "N/A"
        return f"{value:.3f}" if isinstance(value, float) else str(value)

    rows = [
        "| " + " | ".join(frame.columns) + " |",
        "| " + " | ".join(["---"] * len(frame.columns)) + " |",
    ]
    rows.extend(
        "| " + " | ".join(cell(v) for v in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(rows)


def generate_report(root: Path, output_dir: Path | None = None) -> Path:
    """Read existing results only; publish to output/reports or an explicit directory."""
    root = Path(root)
    destination = Path(output_dir) if output_dir is not None else root / "output/reports"
    scores = pd.read_csv(root / "reports/metrics.csv")
    selection = json.loads((root / "reports/model_selection.json").read_text(encoding="utf-8"))
    frozen = json.loads((root / "reports/freeze_manifest.json").read_text(encoding="utf-8"))
    columns = [
        c
        for c in (
            "split",
            "method",
            "mae",
            "wape",
            "bias",
            "coverage80",
            "width80",
            "coverage95",
            "width95",
        )
        if c in scores
    ]
    text = (
        "# Recorded study results / Wyniki zapisanego badania\n\n"
        "UCI Online Retail II, UK, 2009–2011. Recorded sales are not unconstrained demand. "
        "All methods share the frozen product selection and evaluation windows.\n\n"
        + markdown_table(scores[columns])
        + f"\n\nFrozen validation winner: **{selection['winner']}**. Final-test results do not change this choice.\n\n"
        "MAE and interval width are units; WAPE and bias are percentages; coverage is a fraction. "
        "N/A means unavailable, not zero. Validation intervals were unavailable before later calibration.\n\n"
        "Domyślną metodę wybrano na walidacji. Wynik testu nie zmienia wyboru. "
        "Koszty zapasu są hipotetyczne; nie oszacowano zwrotu biznesowego.\n\n"
        "## Frozen provenance\n\n```json\n"
        + json.dumps(frozen, ensure_ascii=False, indent=2)
        + "\n```\n\nThis generated report does not update README.md, docs, demo data or research manifests.\n"
    )
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "study_results.md"
    path.write_text(text, encoding="utf-8")
    return path
