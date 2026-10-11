"""Protect ingestion semantics, SQL accounting and selection chronology."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from demandlab.data import (
    download_source,
    prepare_data,
    protocol_for,
    read_workbook,
    select_products,
    technical_rules,
)

SQL = Path(__file__).resolve().parents[1] / "sql"


def test_all_sheets_aliases_and_physical_row_metadata(tmp_path):
    source = tmp_path / "source.xlsx"
    first = pd.DataFrame(
        {
            "Invoice": ["1", "1"],
            "StockCode": ["A1", "A1"],
            "Description": ["Alpha", "Alpha"],
            "Quantity": [2, 2],
            "InvoiceDate": [pd.Timestamp("2009-12-01")] * 2,
            "Price": [3, 3],
            "Customer ID": [None, None],
            "Country": ["United Kingdom"] * 2,
        }
    )
    second = (
        first.iloc[:1]
        .rename(columns={"Invoice": "InvoiceNo", "Price": "UnitPrice", "Customer ID": "CustomerID"})
        .copy()
    )
    second["InvoiceDate"] = pd.Timestamp("2011-12-09")
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        first.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        second.to_excel(writer, sheet_name="Year 2010-2011", index=False)
    imported, sheets = read_workbook(source)
    assert len(imported) == 3  # identical business rows intentionally retained
    assert len(sheets) == 2
    assert imported["source_row"].tolist() == [2, 3, 2]
    assert imported["date"].min() == pd.Timestamp("2009-12-01")
    assert imported["date"].max() == pd.Timestamp("2011-12-09")
    assert imported["customer_id"].isna().all()
    root = tmp_path / "project"
    cached = download_source(root, source)
    again = download_source(root)
    assert cached == again
    assert cached.read_bytes() == source.read_bytes()


def test_disjoint_sql_reasons_and_hand_calculated_aggregation():
    frame = pd.DataFrame(
        {
            "invoice": ["1", "1", "C2", "3", "4", "5", "6", "7", "8"],
            "sku": ["A1", "A1", "A1", "A1", "A1", "A1", "POST", "A1", "A1"],
            "name": ["product"] * 9,
            "quantity": [2, 2, -2, -1, 0, 4, 1, 8, 3],
            "price": [3, 3, 3, 3, 3, 0, 2, 3, 3],
            "date": pd.to_datetime(["2009-12-01"] * 8 + ["2009-12-02"]),
            "country": ["United Kingdom"] * 7 + ["France", "United Kingdom"],
            "customer_id": [None] * 9,
        }
    )
    with duckdb.connect() as db:
        db.register("frame", frame)
        db.execute("CREATE TABLE source_lines AS SELECT * FROM frame")
        db.execute("CREATE TABLE technical_rules AS SELECT 'POST' AS sku, 'postage' AS rule")
        db.execute((SQL / "classify.sql").read_text())
        db.execute((SQL / "aggregate.sql").read_text())
        reasons = db.execute("SELECT exclusion_reason FROM classified_lines").df()[
            "exclusion_reason"
        ]
        assert len(reasons) == 9
        assert (reasons == "cancellation").sum() == 1
        assert (reasons == "negative_quantity_return_or_adjustment").sum() == 1
        assert (reasons == "technical_code").sum() == 1
        assert (reasons == "accepted").sum() == 3
        daily = db.execute("SELECT * FROM daily_sales ORDER BY date").df()
        assert daily["y"].tolist() == [4.0, 3.0]
        assert daily["y"].sum() == 7.0
        assert (
            db.execute(
                "SELECT sum(quantity*price) FROM classified_lines WHERE exclusion_reason='accepted'"
            ).fetchone()[0]
            == 21
        )


def test_selection_ignores_future_and_technical_rules_only_use_initial():
    start = pd.Timestamp("2009-12-01")
    cutoff = start + pd.Timedelta(days=364)
    rows = []
    for sku in ["A", "B", "C", "D"]:
        for index in range(365):
            if index % (10 if sku in ("A", "B") else 2) == 0:
                rows.append({"sku": sku, "date": start + pd.Timedelta(days=index), "y": 2})
    daily = pd.DataFrame(rows)
    selected = select_products(daily, cutoff, count=4)
    changed = pd.concat(
        [
            daily,
            pd.DataFrame([{"sku": "FUTURE", "date": cutoff + pd.Timedelta(days=1), "y": 999999}]),
        ]
    )
    pd.testing.assert_frame_equal(selected, select_products(changed, cutoff, count=4))
    assert selected.groupby("group").size().to_dict() == {"intermittent": 2, "regular": 2}
    rules_frame = pd.DataFrame(
        {
            "sku": ["POST", "AMAZONFEE", "A1"],
            "name": ["postage", "fee", "product"],
            "date": [start, cutoff + pd.Timedelta(days=1), start],
        }
    )
    assert technical_rules(rules_frame, cutoff) == {"POST": "postage"}


def test_protocol_exact_dates_and_no_selection_overlap():
    protocol = protocol_for(pd.Timestamp("2011-12-08"), pd.Timestamp("2010-11-30"))
    assert protocol["windows"]["final_test"] == {
        "start": "2011-11-11",
        "end": "2011-12-08",
        "origin": "2011-11-10",
    }
    previous_end = None
    for window in protocol["windows"].values():
        start, end = pd.Timestamp(window["start"]), pd.Timestamp(window["end"])
        assert (end - start).days == 27
        assert pd.Timestamp(window["origin"]) == start - pd.Timedelta(days=1)
        if previous_end is not None:
            assert start == previous_end + pd.Timedelta(days=1)
        previous_end = end
    with pytest.raises(ValueError, match="overlaps validation"):
        protocol_for(pd.Timestamp("2011-01-01"), pd.Timestamp("2010-11-30"))


def test_calendar_starts_at_first_sale_and_reconciles_excluding_last_day():
    with duckdb.connect() as db:
        db.execute(
            "CREATE TABLE selected_products AS SELECT 'A1' AS sku, DATE '2010-01-02' AS first_sale"
        )
        db.execute("CREATE TABLE daily_sales(sku VARCHAR, date DATE, y DOUBLE)")
        db.execute(
            "INSERT INTO daily_sales VALUES ('A1', '2010-01-02', 4), ('A1', '2010-01-04', 3), ('A1', '2010-01-05', 999)"
        )
        calendar = db.execute((SQL / "calendar.sql").read_text(), [pd.Timestamp("2010-01-04")]).df()
    assert calendar["date"].min() == pd.Timestamp("2010-01-02")
    assert calendar["date"].max() == pd.Timestamp("2010-01-04")
    assert calendar["y"].tolist() == [4, 0, 3]
    assert calendar["y"].sum() == 7


def test_preparation_is_idempotent_and_retains_missing_customer_duplicates(tmp_path):
    start = pd.Timestamp("2009-12-01")
    records = []
    for group, step in (("I", 10), ("R", 2)):
        for number in range(40):
            for offset in range(0, 365, step):
                records.append(
                    {
                        "Invoice": "100",
                        "StockCode": f"{group}{number:02}",
                        "Description": "Initial name",
                        "Quantity": 2,
                        "InvoiceDate": start + pd.Timedelta(days=offset),
                        "Price": 3,
                        "Customer ID": None,
                        "Country": "United Kingdom",
                    }
                )
    records.append(records[0].copy())  # genuine indistinguishable business line
    source = tmp_path / "source.xlsx"
    first = pd.DataFrame(records)
    second = first.iloc[:1].copy()
    second["InvoiceDate"] = pd.Timestamp("2011-12-09")
    second["Quantity"] = 999
    second["Description"] = "Future name must not replace the initial name"
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        first.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        second.to_excel(writer, sheet_name="Year 2010-2011", index=False)
    root = tmp_path / "project"
    first_manifest = prepare_data(root, source)
    daily = pd.read_parquet(root / "data/processed/daily.parquet")
    second_manifest = prepare_data(root)
    pd.testing.assert_frame_equal(daily, pd.read_parquet(root / "data/processed/daily.parquet"))
    assert first_manifest["source_sha256"] == second_manifest["source_sha256"]
    assert len(second_manifest["selected_skus"]) == 80
    assert daily["y"].sum() == len(first) * 2
    assert daily["date"].max() == pd.Timestamp("2011-12-08")
    assert pd.read_csv(root / "reports/product_selection.csv")["name"].unique().tolist() == [
        "Initial name"
    ]
