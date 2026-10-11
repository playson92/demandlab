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


def method_table(frame, columns):
    result = frame[["method", *columns]].copy()
    result["method"] = result.method.map(method_label)
    return result.rename(
        columns={"method": "Metoda", "mae": "MAE [szt.]", "wape": "WAPE [%]", "bias": "Bias [%]"}
    )
