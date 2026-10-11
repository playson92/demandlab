"""Preserve original test evidence when correcting the displayed bias unit only."""

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from demandlab.pipeline import dump, load
from demandlab.tracking import code_identity

root = Path(__file__).resolve().parents[1]
frozen = load(root / "reports/freeze_manifest.json")
original_code = frozen.get("original_forecasting_code", frozen["code"])
source_sha = original_code["source_sha"]


def committed(name):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{source_sha}:{name}"])


old_app = committed("app/streamlit_app.py").decode("utf-8")
expected_app = old_app.replace("Bias · prognoza−sprzedaż [szt.]", "Bias · prognoza−sprzedaż [%]")
assert (root / "app/streamlit_app.py").read_text(encoding="utf-8") == expected_app
names = subprocess.check_output(
    ["git", "-C", str(root), "ls-tree", "-r", "--name-only", source_sha], text=True
).splitlines()
for name in names:
    if name.startswith(("src/", "sql/", "configs/")) or name in {"pyproject.toml", "uv.lock"}:
        assert (root / name).read_bytes().replace(b"\r\n", b"\n") == committed(name).replace(
            b"\r\n", b"\n"
        ), name
for name in ["freeze_manifest.json", "forecast_manifest.json", "final_test_metrics.csv"]:
    original = root / "reports" / name.replace(".", "_original.", 1)
    if not original.exists():
        original.write_bytes((root / "reports" / name).read_bytes())
original_freeze = root / "reports/freeze_manifest_original.json"
frozen.update(
    {
        "original_forecasting_code": original_code,
        "original_freeze_sha256": hashlib.sha256(original_freeze.read_bytes()).hexdigest(),
        "code": code_identity(root),
        "final_test_exposed": True,
        "correction_recorded_utc": datetime.now(UTC).isoformat(),
        "evaluation_kind": "Post-test presentation correction; original assessment retained; numerical code/forecasts unchanged",
    }
)
dump(root / "reports/freeze_manifest.json", frozen)
forecast_manifest = load(root / "reports/forecast_manifest.json")
forecast_manifest["freeze_sha256"] = hashlib.sha256(
    (root / "reports/freeze_manifest.json").read_bytes()
).hexdigest()
forecast_manifest["post_test_correction"] = "Bias display unit only; original manifest preserved"
dump(root / "reports/forecast_manifest.json", forecast_manifest)
print(
    "Presentation correction recorded; original forecasts, numerical code and original evidence preserved"
)
