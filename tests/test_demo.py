"""The committed genuine demo must work without raw data or a tracking server."""

import json
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_committed_uci_demo_all_views(monkeypatch):
    monkeypatch.delenv("DEMANDLAB_DEMO_DIR", raising=False)
    demo = ROOT / "data/demo"
    manifest = json.loads((demo / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset"] == "UCI Online Retail II 502"
    products = pd.read_csv(demo / "products.csv", dtype={"sku": str})
    assert 50 <= len(products) <= 100
    predictions = pd.read_parquet(demo / "forecasts.parquet")
    assert "y" not in predictions and len(predictions) == len(products) * 28 * 3
    app = AppTest.from_file(str(ROOT / "app/streamlit_app.py"), default_timeout=30).run()
    assert not app.exception and not app.error
    sku = manifest["examples"]["regular"]
    app.sidebar.selectbox[0].set_value(sku).run()
    for view in ["Prognoza produktu", "Jakość modeli", "Symulator"]:
        app.sidebar.radio[0].set_value(view).run()
        assert not app.exception and not app.error
    app.number_input(key="lead_time").set_value(1).run()
    assert not app.exception and not app.error
