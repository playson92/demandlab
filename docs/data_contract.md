# Recorded sales contract

DemandLab uses **UCI Online Retail II, dataset 502**, both workbook sheets covering
December 2009–December 2011. It is not the shorter Online Retail dataset. The
official source, DOI and CC BY 4.0 attribution are in [DATA_LICENSE](../DATA_LICENSE.md).

`daily_recorded_sales_units` is the sum of positive Quantity from valid,
non-cancelled United Kingdom product lines with positive unit price. It measures
recorded sales, not uncensored demand, customer orders, stock availability or revenue.
Later returns do not alter earlier sales. Large valid transactions are retained.

The reader recognizes Invoice/InvoiceNo, Price/UnitPrice and Customer ID/CustomerID
aliases. All transaction sheets must satisfy the schema. Local source_sheet and
source_row identify physical input lines; neither invoices nor customer IDs are
published. Source timestamps are naive local transaction times; no timezone is
invented. Raw and interim artifacts stay outside Git.

SQL uses first-match, disjoint exclusion reasons: other country, invalid date,
missing SKU, missing invoice, cancellation prefix C (case insensitive), invalid
quantity, negative quantity (return or adjustment), zero quantity, invalid price,
nonpositive price, technical code, accepted. A cancelled negative-quantity line is
counted once as cancellation. The exact explicit technical-code list is recorded
in the manifest and activated only for codes observed in the initial 365 days.
Gift voucher accounting codes require a matching initial description. Genuine
alphanumeric merchandise is retained. Missing CustomerID alone never rejects a line.

Business-identical rows are retained because the source lacks a line ID. Their
count is reported, while an import replaces one source table instead of appending
it. Thus repeated pipeline calls do not multiply transactions.

Selection uses only the first 365 calendar days (inclusive): at least 180 available
days since first positive sale, at least 20 positive days. The positive-day share
splits products below 40% (intermittent) and at least 40% (regular). Forty per group
are selected by initial units descending, SKU ascending; a short group is filled
from remaining eligible products. Names are the most frequent accepted initial
description, with alphabetic tie breaking. Selection and groups never change on
later inactivity or test outcomes.

`data/processed/daily.parquet` contains `sku` (string), `date` (local date), `y`
(nonnegative recorded units). Each selected SKU has a calendar from its first
positive sale through D, the last source date minus one day. There are no zeros
before first sale. Internal absent sales are treated as zero **under the explicit
source completeness assumption**; a prior transaction date does not prove that
all sales or demand were observable. The last source day is conservatively removed
before evaluation as potentially incomplete.

DuckDB performs classification, daily aggregation, calendar generation and
quantity reconciliation. `reports/reconciliation.json` contains counts, quantity
and GBP value by disjoint reason, missingness, potential duplicates, pretest-only
extremes, and equal line/daily totals for the same SKU/country/date scope.
`reports/data_manifest.json` records source URL, retrieval timestamp, byte size,
SHA-256, sheet headers/counts and source date range. `configs/protocol.json` fixes
the seven consecutive 28-day evaluation windows and selection cutoff before any
model evaluation. Quantities and values across excluded rows are accounting
diagnostics and can be negative; daily targets are always nonnegative.
