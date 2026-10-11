"""Read and validate the bundled demo, without training or network access."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

METHODS = frozenset({"seasonal_naive_7", "weekday_mean_4w", "hist_gradient_boosting"})
FILES = (
    "manifest.json",
    "daily.parquet",
    "forecasts.parquet",
    "actuals.parquet",
    "products.csv",
    "metrics.csv",
)
RESTORE = (
    "Przywróć komplet plików data/demo z dołączonego projektu albo pobierz "
    "ponownie tę samą, kompletną gałąź repozytorium."
)


class ArtifactError(ValueError):
    """Demo artifacts are unavailable or inconsistent."""


def artifact_version(directory: Path) -> tuple:
    try:
        return tuple(
            (name, (directory / name).stat().st_mtime_ns, (directory / name).stat().st_size)
            for name in FILES
        )
    except OSError as exc:
        raise ArtifactError(f"Brakuje plików demo. {RESTORE}") from exc


def _dates(values, label):
    result = pd.to_datetime(values, errors="raise")
    if (
        result.isna().any()
        or result.dt.tz is not None
        or not result.eq(result.dt.normalize()).all()
    ):
        raise ArtifactError(
            f"Nieprawidłowe daty w pliku {label}; wymagane pełne dni bez strefy czasowej."
        )
    return result


def load_artifacts(directory: Path) -> dict:
    """Return validated tables and their original manifest; never drop unmatched rows."""
    try:
        artifact_version(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ArtifactError("Manifest demo musi być obiektem JSON.")
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
            raise ArtifactError("Niezgodna wersja artefaktów. Wymagana schema_version=1.")
        if not {"winner", "source_sha", "test_origin"}.issubset(manifest):
            raise ArtifactError("Manifest nie zawiera metody, originu lub identyfikacji źródła.")
        if not isinstance(manifest["source_sha"], str) or not manifest["source_sha"].strip():
            raise ArtifactError("Manifest zawiera nieprawidłową identyfikację źródła.")
        origin = pd.Timestamp(manifest["test_origin"])
        if pd.isna(origin) or origin.tz is not None or origin != origin.normalize():
            raise ArtifactError("Manifest zawiera nieprawidłowy origin.")
        end = origin + pd.Timedelta(days=28)
        if "D" in manifest and pd.Timestamp(manifest["D"]) != end:
            raise ArtifactError("Data D w manifeście nie odpowiada końcowi horyzontu 28 dni.")
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
                if (
                    data[name].sku.isna().any()
                    or data[name].sku.astype(str).str.strip().eq("").any()
                ):
                    raise ArtifactError(f"Nieprawidłowe SKU w pliku {name}.")
                data[name]["sku"] = data[name].sku.astype(str)
        products = data["products"]
        if products.empty or products.sku.duplicated().any():
            raise ArtifactError("Lista produktów jest pusta lub zawiera powtórzone SKU.")
        skus = set(products.sku)
        expected_dates = pd.date_range(origin + pd.Timedelta(days=1), end)
        for name in ("daily", "actuals", "forecasts"):
            if set(data[name].sku) != skus:
                raise ArtifactError(f"Zestaw SKU w pliku {name} nie odpowiada liście produktów.")
        for name in ("daily", "actuals"):
            frame = data[name]
            frame["date"] = _dates(frame.date, name)
            if frame.duplicated(["sku", "date"]).any():
                raise ArtifactError(f"Powtórzone dzienne agregaty w pliku {name}.")
            values = frame.y.to_numpy(dtype=float)
            if (
                not np.isfinite(values).all()
                or (values < 0).any()
                or (values != np.floor(values)).any()
            ):
                raise ArtifactError(f"Nieprawidłowa liczba sztuk w pliku {name}.")
            for _, series in frame.groupby("sku"):
                dates = pd.DatetimeIndex(series.date.sort_values())
                if name == "actuals" and not dates.equals(expected_dates):
                    raise ArtifactError(
                        "Actuals musi zawierać pełne 28 dni każdego SKU, dokładnie origin + 1…28."
                    )
                if name == "daily" and (
                    dates.min() > origin
                    or dates.max() not in (origin, end)
                    or not dates.equals(pd.date_range(dates.min(), dates.max()))
                ):
                    raise ArtifactError(
                        "Historia daily musi być ciągła dla każdego SKU i kończyć się w originie lub dniu D."
                    )
        daily = data["daily"]
        actuals = data["actuals"]
        observed = daily.loc[daily.date > origin]
        if not observed.empty:
            comparison = observed.merge(
                actuals,
                on=["sku", "date"],
                how="left",
                validate="one_to_one",
                suffixes=("_daily", "_actual"),
            )
            if (
                comparison.y_actual.isna().any()
                or not comparison.y_daily.eq(comparison.y_actual).all()
            ):
                raise ArtifactError("Sprzedaż w daily i actuals nie jest zgodna dla wspólnych dat.")
        forecasts = data["forecasts"]
        for column in ("origin", "target_date"):
            forecasts[column] = _dates(forecasts[column], "forecasts")
        if "y" in forecasts:
            raise ArtifactError(
                "Tabela prognoz zawiera etykiety; oczekiwano oddzielnej tabeli actuals."
            )
        if not forecasts.origin.eq(origin).all():
            raise ArtifactError("Origin prognoz nie odpowiada originowi w manifeście.")
        if set(forecasts.method) != METHODS or manifest["winner"] not in METHODS:
            raise ArtifactError(
                "Brakuje wymaganych metod prognozy lub domyślna metoda manifestu jest nieprawidłowa."
            )
        if forecasts["split"].isna().any() or not forecasts["split"].eq("final_test").all():
            raise ArtifactError("Prognozy demo muszą należeć do zamrożonego testu końcowego.")
        if (
            not np.isfinite(forecasts.prediction.to_numpy(dtype=float)).all()
            or (forecasts.prediction < 0).any()
        ):
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
        for sku in skus:
            for method in METHODS:
                frame = forecasts.loc[forecasts.sku.eq(sku) & forecasts.method.eq(method)]
                if sorted(frame.horizon.tolist()) != list(range(1, 29)):
                    raise ArtifactError(
                        "Każdy SKU i każda metoda musi zawierać pełne 28 dni prognozy."
                    )
                if not frame.target_date.eq(
                    frame.origin + pd.to_timedelta(frame.horizon, unit="D")
                ).all():
                    raise ArtifactError("Daty prognozy nie zgadzają się z originem i horyzontem.")
        metrics = data["metrics"]
        if (
            metrics.empty
            or metrics.duplicated(["split", "method"]).any()
            or set(metrics.method) != METHODS
            or metrics["split"].isna().any()
            or any(set(frame.method) != METHODS for _, frame in metrics.groupby("split"))
        ):
            raise ArtifactError("Tabela metrics zawiera nieprawidłowe lub niekompletne metody.")
        numeric_columns = required["metrics"] - {"split", "method"}
        numeric_columns |= set(metrics.columns) & {
            "bias",
            "n",
            "pinball_q025",
            "pinball_q10",
            "pinball_q90",
            "pinball_q975",
        }
        for column in numeric_columns:
            values = metrics[column].to_numpy(dtype=float)
            if np.isinf(values).any():
                raise ArtifactError("Tabela metrics zawiera nieskończone wartości.")
        data["manifest"] = manifest
        return data
    except ArtifactError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ArtifactError(
            f"Nie można odczytać artefaktów demo. Sprawdź kompletność i manifest danych. {RESTORE}"
        ) from exc
