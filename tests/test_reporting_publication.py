import hashlib
import json

import pandas as pd

from demandlab.reporting import generate_report


def test_publication_preserves_editorial_and_frozen_artifacts(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "data/demo").mkdir(parents=True)
    (tmp_path / "README.md").write_text("Editorial README", encoding="utf-8")
    (tmp_path / "docs/results.md").write_text("Editorial results", encoding="utf-8")
    (tmp_path / "data/demo/manifest.json").write_text('{"immutable":true}', encoding="utf-8")
    pd.DataFrame(
        [{"split": "validation", "method": "weekday_mean_4w", "mae": 2.0, "wape": 30.0}]
    ).to_csv(tmp_path / "reports/metrics.csv", index=False)
    (tmp_path / "reports/model_selection.json").write_text(
        json.dumps({"winner": "weekday_mean_4w"}), encoding="utf-8"
    )
    (tmp_path / "reports/freeze_manifest.json").write_text(
        '{"source_sha":"frozen"}', encoding="utf-8"
    )
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()
    }
    published = generate_report(tmp_path)
    assert published == tmp_path / "output/reports/study_results.md"
    assert "Domyślną" in published.read_text(encoding="utf-8")
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert generate_report(tmp_path, tmp_path / "output/explicit").is_file()
