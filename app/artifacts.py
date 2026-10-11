"""Strict demo artifact loading without network, training or fallback data."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


class ArtifactError(ValueError):
    """Demo artifacts are unavailable or inconsistent."""


def artifact_version(directory: Path) -> tuple:
    names = (
        "manifest.json",
        "daily.parquet",
        "forecasts.parquet",
        "actuals.parquet",
        "products.csv",
        "metrics.csv",
    )
    try:
        return tuple(
            (name, (directory / name).stat().st_mtime_ns, (directory / name).stat().st_size)
            for name in names
        )
    except OSError as exc:
        raise ArtifactError(
            "Brakuje plików demo. Odtwórz artefakty komendą python -m demandlab demo."
        ) from exc


def load_artifacts(directory: Path) -> dict:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise ArtifactError("Niezgodna wersja artefaktów. Wymagana schema_version=1.")
        if not {"winner", "source_sha", "test_origin"}.issubset(manifest):
            raise ArtifactError("Manifest nie zawiera metody, originu lub identyfikacji źródła.")
        test_origin = pd.Timestamp(manifest["test_origin"])
        if pd.isna(test_origin):
            raise ArtifactError("Manifest zawiera nieprawidłowy origin.")
        data = {
            name: pd.read_parquet(directory / f"{name}.parquet")
            for name in ("daily", "forecasts", "actuals")
        }
        data["products"] = pd.read_csv(directory / "products.csv", dtype={"sku": str})
        data["metrics"] = pd.read_csv(directory / "metrics.csv")
        required = {
            "daily": {"sku", "date", "y"},
            "actuals": {"sku", "date", "y"},
            "products": {"sku", "name", "group"},
            "metrics": {
                "split",
                "method",
                "mae",
                "wape",
                "coverage80",
                "width80",
                "coverage95",
                "width95",
            },
            "forecasts": {
                "sku",
                "origin",
                "target_date",
                "horizon",
                "method",
                "prediction",
                "q025",
                "q10",
                "q90",
                "q975",
                "split",
                "run_id",
            },
        }
        for name, columns in required.items():
            if not columns.issubset(data[name].columns):
                raise ArtifactError(f"Nieprawidłowy schemat pliku {name}; brak wymaganych kolumn.")
            if "sku" in data[name]:
                data[name]["sku"] = data[name]["sku"].astype(str)
        for name in ("daily", "actuals"):
            data[name]["date"] = pd.to_datetime(data[name]["date"])
            if data[name].duplicated(["sku", "date"]).any():
                raise ArtifactError(f"Powtórzone dzienne agregaty w pliku {name}.")
            values = data[name].y.to_numpy(dtype=float)
            if (
                not np.isfinite(values).all()
                or (values < 0).any()
                or (values != np.floor(values)).any()
            ):
                raise ArtifactError(f"Nieprawidłowa liczba sztuk w pliku {name}.")
        if data["products"].empty or data["products"].sku.duplicated().any():
            raise ArtifactError("Lista produktów jest pusta lub zawiera powtórzone SKU.")
        for column in ("origin", "target_date"):
            data["forecasts"][column] = pd.to_datetime(data["forecasts"][column])
        forecasts = data["forecasts"]
        if "y" in forecasts:
            raise ArtifactError(
                "Tabela prognoz zawiera etykiety; oczekiwano oddzielnej tabeli actuals."
            )
        if not np.isfinite(forecasts.prediction).all() or (forecasts.prediction < 0).any():
            raise ArtifactError("Prognozy muszą być skończone i nieujemne.")
        bounds = forecasts[["q025", "q10", "q90", "q975"]]
        complete = bounds.notna().all(axis=1)
        if (bounds.notna().any(axis=1) & ~complete).any():
            raise ArtifactError("Niekompletne granice przedziałów prognozy.")
        available = bounds[complete].to_numpy(dtype=float)
        if (
            not np.isfinite(available).all()
            or (available < 0).any()
            or (np.diff(available, axis=1) < 0).any()
        ):
            raise ArtifactError("Granice przedziałów są nieprawidłowe lub niezagnieżdżone.")
        if forecasts.duplicated(["sku", "origin", "method", "horizon"]).any():
            raise ArtifactError("Powtórzone wiersze prognozy.")
        for _, frame in forecasts.groupby(["sku", "origin", "method"]):
            if sorted(frame.horizon.tolist()) != list(range(1, 29)):
                raise ArtifactError("Każda prognoza musi zawierać pełne 28 dni.")
            if not (
                frame.target_date == frame.origin + pd.to_timedelta(frame.horizon, unit="D")
            ).all():
                raise ArtifactError("Daty prognozy nie zgadzają się z originem i horyzontem.")
        if manifest.get("winner") not in forecasts.method.unique():
            raise ArtifactError("Brakuje prognozy domyślnej metody wskazanej w manifeście.")
        data["manifest"] = manifest
        return data
    except ArtifactError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArtifactError(
            "Nie można odczytać artefaktów demo. Sprawdź kompletność i manifest danych."
        ) from exc
