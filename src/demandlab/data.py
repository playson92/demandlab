"""Official UCI Online Retail II ingestion and auditable recorded-sales aggregation."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SOURCE_URL = "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip"
SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
ALIASES = {
    "Invoice": "invoice",
    "InvoiceNo": "invoice",
    "StockCode": "sku",
    "Description": "name",
    "Quantity": "quantity",
    "InvoiceDate": "timestamp",
    "Price": "price",
    "UnitPrice": "price",
    "Customer ID": "customer_id",
    "CustomerID": "customer_id",
    "Country": "country",
}
# A closed list of non-product codes, activated only if seen in initial history.
# Alphanumeric merchandise codes are deliberately retained.
TECHNICAL_CODES = {
    "POST": "postage",
    "D": "discount",
    "M": "manual adjustment",
    "C2": "carriage",
    "BANK CHARGES": "bank charge",
    "DOT": "dotcom postage",
    "AMAZONFEE": "marketplace fee",
    "ADJUST": "adjustment",
    "ADJUST2": "adjustment",
    "CRUK": "charity accounting",
    "S": "sample accounting",
    "TEST001": "test record",
    "TEST002": "test record",
}


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )


def sha256(path: Path) -> str:
    """Identify the bytes used; this is not publisher-signature verification."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_source(root: Path, source_file: Path | None = None) -> Path:
    """Cache one original XLSX, with bounded network retries and a local alternative."""
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / "online_retail_II.xlsx"
    metadata = raw / "download.json"
    if source_file is not None:
        source_file = Path(source_file).resolve()
        if not source_file.is_file() or source_file.suffix.lower() != ".xlsx":
            raise ValueError("--source-file must name an existing XLSX workbook")
        if source_file != target.resolve():
            shutil.copyfile(source_file, target)
        _json(
            metadata,
            {
                "url": SOURCE_URL,
                "mode": "local_source_file",
                "retrieved_at_utc": datetime.now(UTC).isoformat(),
            },
        )
    elif target.exists() and zipfile.is_zipfile(target):
        return target
    else:
        archive = raw / "download.part"
        last_error = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    SOURCE_URL, headers={"User-Agent": "DemandLab/1.0"}
                )
                with (
                    urllib.request.urlopen(request, timeout=90) as response,
                    archive.open("wb") as output,
                ):
                    shutil.copyfileobj(response, output)
                with zipfile.ZipFile(archive) as zipped:
                    members = [name for name in zipped.namelist() if name.lower().endswith(".xlsx")]
                    if len(members) != 1:
                        raise ValueError("Official archive must contain exactly one XLSX workbook")
                    with zipped.open(members[0]) as input_file, target.open("wb") as output:
                        shutil.copyfileobj(input_file, output)
                _json(
                    metadata,
                    {
                        "url": SOURCE_URL,
                        "mode": "official_download",
                        "retrieved_at_utc": datetime.now(UTC).isoformat(),
                    },
                )
                archive.unlink(missing_ok=True)
                break
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                last_error = error
                archive.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(2**attempt)
        else:
            raise RuntimeError(
                "UCI download failed after 3 attempts; use --source-file"
            ) from last_error
    if not zipfile.is_zipfile(target):
        raise ValueError("Source file is not a valid XLSX archive")
    return target


def read_workbook(path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read every transaction sheet once and preserve spreadsheet row provenance."""
    frames, sheets = [], []
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        for sheet in workbook.sheet_names:
            frame = pd.read_excel(workbook, sheet_name=sheet, dtype=object)
            original_columns = [str(column).strip() for column in frame.columns]
            frame.columns = original_columns
            mapped = [ALIASES.get(column, column) for column in original_columns]
            if not {"invoice", "sku", "quantity", "timestamp", "price", "country"}.issubset(mapped):
                raise ValueError(f"Unexpected sheet schema: {sheet}: {original_columns}")
            if len(set(mapped)) != len(mapped):
                raise ValueError(f"Ambiguous aliases in sheet {sheet}")
            frame.columns = mapped
            if "customer_id" not in frame:
                frame["customer_id"] = None
            if "name" not in frame:
                frame["name"] = None
            frame["source_sheet"] = sheet
            frame["source_row"] = np.arange(2, len(frame) + 2)
            sheets.append({"name": sheet, "rows": len(frame), "headers": original_columns})
            frames.append(frame)
    if not frames:
        raise ValueError("Workbook has no transaction sheets")
    result = pd.concat(frames, ignore_index=True)
    for column in ("invoice", "sku", "country", "name"):
        result[column] = result[column].astype("string").str.strip()
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    if result["timestamp"].dt.tz is not None:
        raise ValueError("Unexpected timezone: source dates must be local naive transaction dates")
    result["date"] = result["timestamp"].dt.normalize()
    for column in ("quantity", "price"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        result.loc[~np.isfinite(result[column]), column] = np.nan
    return result, sheets


def technical_rules(frame: pd.DataFrame, cutoff: pd.Timestamp) -> dict[str, str]:
    """Freeze explicit technical-code rules using only the initial history."""
    initial = frame.loc[frame["date"] <= cutoff]
    observed = set(initial["sku"].dropna())
    rules = {code: reason for code, reason in TECHNICAL_CODES.items() if code in observed}
    vouchers = (
        initial.loc[
            initial["sku"].str.match(r"(?i)^gift_\d+$", na=False)
            & initial["name"].str.contains("gift voucher", case=False, na=False),
            "sku",
        ]
        .dropna()
        .unique()
    )
    rules.update({code: "gift voucher accounting" for code in vouchers})
    return dict(sorted(rules.items()))


def select_products(daily: pd.DataFrame, cutoff: pd.Timestamp, count: int = 80) -> pd.DataFrame:
    """Choose products solely from their available first-365-day sales history."""
    initial = daily.loc[daily["date"] <= cutoff].copy()
    initial = initial.loc[initial["y"] > 0]
    stats = (
        initial.groupby("sku", sort=True)
        .agg(
            first_sale=("date", "min"),
            positive_days=("date", "nunique"),
            initial_units=("y", "sum"),
        )
        .reset_index()
    )
    stats["history_days"] = (cutoff - stats["first_sale"]).dt.days + 1
    stats["positive_day_share"] = stats["positive_days"] / stats["history_days"]
    stats = stats.loc[(stats["history_days"] >= 180) & (stats["positive_days"] >= 20)].copy()
    stats["group"] = np.where(stats["positive_day_share"] < 0.4, "intermittent", "regular")
    stats = stats.sort_values(["initial_units", "sku"], ascending=[False, True])
    quota = count // 2
    selected = pd.concat(
        [stats.loc[stats["group"] == group].head(quota) for group in ("intermittent", "regular")]
    )
    remaining = stats.loc[~stats["sku"].isin(selected["sku"])]
    selected = pd.concat([selected, remaining.head(count - len(selected))])
    if len(selected) < count:
        raise ValueError(f"Only {len(selected)} eligible products; expected {count}")
    selected["selection_cutoff"] = cutoff.date().isoformat()
    return selected.sort_values("sku").reset_index(drop=True)


def protocol_for(last_date: pd.Timestamp, selection_cutoff: pd.Timestamp) -> dict:
    """Fix all inclusive evaluation windows before any modeling."""
    offsets = [
        ("validation_1", 195, 168),
        ("validation_2", 167, 140),
        ("validation_3", 139, 112),
        ("validation_4", 111, 84),
        ("calibration_1", 83, 56),
        ("calibration_2", 55, 28),
        ("final_test", 27, 0),
    ]
    windows = {}
    for name, start, end in offsets:
        first = last_date - pd.Timedelta(days=start)
        windows[name] = {
            "start": first.date().isoformat(),
            "end": (last_date - pd.Timedelta(days=end)).date().isoformat(),
            "origin": (first - pd.Timedelta(days=1)).date().isoformat(),
        }
    if selection_cutoff >= pd.Timestamp(windows["validation_1"]["start"]):
        raise ValueError("Initial selection overlaps validation; source history is too short")
    return {
        "schema_version": 1,
        "D": last_date.date().isoformat(),
        "selection_cutoff": selection_cutoff.date().isoformat(),
        "horizon": 28,
        "last_source_day_excluded": True,
        "windows": windows,
        "target": "daily_recorded_sales_units",
        "country": "United Kingdom",
    }


def _sql(root: Path, name: str) -> str:
    path = root / "sql" / name
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "sql" / name
    return path.read_text(encoding="utf-8")


def prepare_data(root: Path, source_file: Path | None = None) -> dict:
    """Replace derived tables from one workbook, reconcile SQL totals, and freeze selection."""
    root = Path(root).resolve()
    source = download_source(root, source_file)
    source_hash = sha256(source)
    frame, sheets = read_workbook(source)
    if frame["date"].notna().sum() == 0:
        raise ValueError("Source has no valid transaction dates")
    first_date, raw_last = frame["date"].min(), frame["date"].max()
    last_date = raw_last - pd.Timedelta(days=1)
    cutoff = first_date + pd.Timedelta(days=364)
    protocol = protocol_for(last_date, cutoff)
    rules = technical_rules(frame, cutoff)
    technical = pd.DataFrame({"sku": list(rules), "rule": list(rules.values())}, dtype="string")
    for directory in ("data/interim", "data/processed", "reports", "configs"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(root / "data" / "interim" / "retail.duckdb"))
    try:
        connection.register("source_frame", frame)
        connection.register("technical_rules_frame", technical)
        connection.execute("CREATE OR REPLACE TABLE source_lines AS SELECT * FROM source_frame")
        connection.execute(
            "CREATE OR REPLACE TABLE technical_rules AS SELECT * FROM technical_rules_frame"
        )
        connection.execute(_sql(root, "classify.sql"))
        connection.execute(_sql(root, "aggregate.sql"))
        daily = connection.execute("SELECT * FROM daily_sales ORDER BY sku, date").df()
        selected = select_products(daily, cutoff)
        # Names are chosen from accepted initial history only, with stable count/name ties.
        names = connection.execute(
            """
            SELECT sku, name FROM (
                SELECT sku, name, count(*) AS n,
                       row_number() OVER (PARTITION BY sku ORDER BY count(*) DESC, name ASC) AS rank
                FROM classified_lines WHERE exclusion_reason='accepted' AND date <= ?
                  AND name IS NOT NULL AND name <> '' GROUP BY sku, name
            ) WHERE rank=1
        """,
            [cutoff],
        ).df()
        selected = selected.merge(names, on="sku", how="left")
        selected["name"] = selected["name"].fillna(selected["sku"])
        selected = selected[
            [
                "sku",
                "name",
                "group",
                "first_sale",
                "history_days",
                "positive_days",
                "positive_day_share",
                "initial_units",
                "selection_cutoff",
            ]
        ]
        connection.register("selection_frame", selected)
        connection.execute(
            "CREATE OR REPLACE TABLE selected_products AS SELECT * FROM selection_frame"
        )
        calendar = connection.execute(_sql(root, "calendar.sql"), [last_date]).df()
        totals = connection.execute(_sql(root, "reconcile.sql"), [last_date]).df().iloc[0].to_dict()
        totals = {
            key: int(value) if float(value).is_integer() else float(value)
            for key, value in totals.items()
        }
        if not np.isclose(totals["line_units"], totals["daily_units"], rtol=0, atol=1e-8):
            raise AssertionError("Accepted line units do not reconcile to daily units")
        calendar.to_parquet(root / "data/processed/daily.parquet", index=False)
        selected.to_csv(root / "reports/product_selection.csv", index=False)
        reasons = connection.execute("""
            SELECT exclusion_reason, count(*) AS rows, coalesce(sum(quantity),0) AS units,
                   coalesce(sum(quantity*price),0) AS value_gbp
            FROM classified_lines GROUP BY exclusion_reason ORDER BY exclusion_reason
        """).df()
        business_columns = [
            "invoice",
            "sku",
            "name",
            "quantity",
            "timestamp",
            "price",
            "customer_id",
            "country",
        ]
        potential_duplicates = int(frame.duplicated(business_columns, keep="first").sum())
        # Quality summaries are constrained to pretest history; integrity totals use predefined rules.
        pretest = frame.loc[
            frame["date"] < pd.Timestamp(protocol["windows"]["final_test"]["start"])
        ]
        reconciliation = {
            "schema_version": 1,
            "status": "PASS",
            "source_rows": len(frame),
            "reason_precedence": [
                "other_country",
                "invalid_date",
                "missing_sku",
                "missing_invoice",
                "cancellation",
                "invalid_quantity",
                "negative_quantity_return_or_adjustment",
                "zero_quantity",
                "invalid_price",
                "nonpositive_price",
                "technical_code",
                "accepted",
            ],
            "disjoint_reasons": reasons.to_dict(orient="records"),
            "missing_by_column": {
                column: int(frame[column].isna().sum()) for column in business_columns
            },
            "potential_duplicate_business_rows_retained": potential_duplicates,
            "selected_same_scope": totals,
            "selected_daily_rows": len(calendar),
            "internal_zero_sales_days": int((calendar["y"] == 0).sum()),
            "pretest_extremes": {
                "max_positive_quantity": float(pretest["quantity"].max()),
                "max_positive_price": float(pretest["price"].max()),
            },
            "large_transactions": "retained without clipping",
            "missing_customer_ids": "retained when the sales line is otherwise valid",
            "duplicate_policy": "business duplicates retained; source table replaced, never appended",
        }
        _json(root / "reports/reconciliation.json", reconciliation)
        download_metadata = json.loads(
            (root / "data/raw/download.json").read_text(encoding="utf-8")
        )
        manifest = {
            "schema_version": 1,
            "dataset": "UCI Online Retail II",
            "dataset_id": 502,
            "doi": "10.24432/C5CG6D",
            "source_page": SOURCE_PAGE,
            **download_metadata,
            "source_sha256": source_hash,
            "size_bytes": source.stat().st_size,
            "hash_claim": "identity of local input bytes, not independently verified publisher signature",
            "sheets": sheets,
            "source_rows": len(frame),
            "date_min": first_date.date().isoformat(),
            "date_max": raw_last.date().isoformat(),
            "D": last_date.date().isoformat(),
            "selection_cutoff": cutoff.date().isoformat(),
            "selected_skus": selected["sku"].tolist(),
            "technical_codes_initial_history": rules,
            "calendar_assumption": "internal absent transactions mean zero recorded sales; completeness is assumed",
            "timezone": "none supplied; local naive transaction dates",
            "target": "daily_recorded_sales_units",
            "license": "CC BY 4.0",
        }
        _json(root / "reports/data_manifest.json", manifest)
        _json(root / "configs/protocol.json", protocol)
        return manifest
    finally:
        connection.close()
