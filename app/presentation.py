"""Shared, stable labels and visual conventions; no research calculations."""

import pandas as pd

METHODS = {
    "seasonal_naive_7": ("Powtórzenie ostatniego tygodnia", "#936120", "dash"),
    "weekday_mean_4w": ("Średnia dnia tygodnia z 4 tygodni", "#247452", "solid"),
    "hist_gradient_boosting": ("Model drzewiasty", "#5264A1", "dot"),
}
VIEWS = {
    "product": "Produkt i prognoza",
    "inventory": "Scenariusze zapasu",
    "methods": "Metody i wyniki",
}
GROUPS = {"regular": "Regularna sprzedaż", "intermittent": "Nieregularna sprzedaż"}


def method_label(method):
    return METHODS[method][0]


def display(value, suffix="", digits=2):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",") + suffix


def measure_digits(field):
    return 0 if field in {"unserved_units", "ending_stock"} else 2


def format_metrics(frame):
    result = frame.copy()
    for column in ("mae", "wape", "bias"):
        if column in result:
            result[column] = result[column].map(display)
    return result


def method_table(frame, columns, formatted=False):
    result = frame[["method", *columns]].copy()
    if formatted:
        result = format_metrics(result)
    result["method"] = result.method.map(method_label)
    return result.rename(
        columns={"method": "Metoda", "mae": "MAE [szt.]", "wape": "WAPE [%]", "bias": "Bias [%]"}
    )
