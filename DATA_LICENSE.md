# Dataset attribution and license

Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository.
[DOI: 10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D).
[Official dataset 502](https://archive.ics.uci.edu/dataset/502/online+retail+ii).

The dataset is distributed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
This applies to the actual aggregated data and forecasts included in this project.
The project's own software uses MIT (see LICENSE); it does not relicense the source data.

Transformations: both original workbook sheets are combined; United Kingdom sales are
filtered by documented validity rules; explicit technical codes are removed; positive
units are aggregated daily; products are selected from the first 365 days; internal
days without recorded sales are filled with zero; the last source day is excluded.
The source workbook, invoices and customer identifiers are never published here.
The SHA-256 manifest identifies the actual input bytes and is not an independent
verification of a publisher signature. No endorsement by the creator or UCI is implied.
