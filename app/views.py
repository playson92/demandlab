"""Three analytical views using frozen files and the unchanged inventory engine."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from charts import forecast_chart, inventory_chart, style
from presentation import (
    METHODS,
    display,
    format_metrics,
    measure_digits,
    method_label,
    method_table,
)
from state import (
    changed_parameters,
    example_parameters,
    inventory_context,
    reset_parameters,
    synchronize_context,
)

from demandlab.inventory import InventoryParameters, simulate


def show_table(frame, **kwargs):
    st.caption("Więcej kolumn? Przesuń tabelę poziomo, aby odczytać wszystkie wyniki.")
    st.dataframe(frame, width="stretch", **kwargs)


def product_view(data, history, final, observed, origin, sku, method, methods):
    with st.container(horizontal=True, vertical_alignment="bottom"):
        days = st.selectbox(
            "Historia [dni]", [28, 84, 180], key="history_days", width=150, persist_state="session"
        )
        interval = st.selectbox(
            "Przedział nominalny",
            ["80%", "95%", "Brak"],
            key="interval",
            width=170,
            persist_state="session",
        )
        actual = st.toggle(
            "Sprzedaż testowa", value=True, key="show_actual", persist_state="session"
        )
        compare = st.toggle("Porównaj metody", key="compare_methods", persist_state="session")
    selected, band = [method], method
    if compare:
        selected = st.multiselect(
            "Porównywane metody",
            methods,
            default=methods,
            format_func=method_label,
            key="forecast_methods",
            persist_state="session",
        )
        if not selected:
            st.info("Wybierz co najmniej jedną metodę.")
            return
        band = st.selectbox(
            "Pasmo dla jednej metody", selected, format_func=method_label, key="band_method"
        )
    frame = history.tail(days)
    st.plotly_chart(
        forecast_chart(frame, final, observed, origin, selected, band, interval, actual),
        width="stretch",
        key="forecast_chart",
        alt="Historia sprzedaży, granica wiedzy, prognoza i jeden przedział; pełny zakres obejmuje piki",
        config={"displaylogo": False},
    )
    st.caption(
        f"Zakres: {frame.date.min():%d.%m.%Y}–{final.target_date.max():%d.%m.%Y}. Zoom: zakres widoczny na osi; dwuklik przywraca całość. Granica wiedzy: {origin:%d.%m.%Y}."
    )
    with st.container(horizontal=True):
        st.button(
            "Sprawdź scenariusz zapasu",
            type="primary",
            key="goto_inventory",
            on_click=lambda: st.session_state.update(view="inventory"),
            icon=":material/inventory_2:",
        )
        table = final[final.method.isin(selected)]
        st.download_button(
            "Prognoza · CSV",
            table.to_csv(index=False),
            f"forecast_{sku}.csv",
            "text/csv",
            key="forecast_csv",
            icon=":material/download:",
        )
    with st.expander("Zapisane wartości prognozy"):
        show_table(table, hide_index=True, alt="Prognozy i granice przedziałów")


def inventory_view(data, history, final, observed, origin, sku, method, methods):
    settings, output = st.columns([1, 2.5], gap="medium")
    with settings:
        scenario = st.selectbox(
            "Ścieżka sprzedaży",
            ["historical", "reference"],
            format_func=lambda s: (
                "Historyczna · sprzedaż testowa"
                if s == "historical"
                else "Hipotetyczna · wspólna referencja"
            ),
            key="scenario",
            persist_state="session",
        )
        multiplier = 1.0
        reference = final[final.method == data["manifest"]["winner"]].sort_values("horizon")
        if scenario == "reference":
            multiplier = st.slider(
                "Mnożnik wspólnej referencji",
                0.0,
                2.0,
                1.0,
                0.1,
                key="multiplier",
                persist_state="session",
            )
        sales = (
            observed.y.to_numpy()
            if scenario == "historical"
            else np.floor(reference.prediction.to_numpy() * multiplier + 0.5)
        )
        context = (*inventory_context(sku, origin, method, sales), scenario, multiplier)
        defaults = example_parameters(history)
        if synchronize_context(st.session_state, sku, defaults, context):
            st.caption("Nowy produkt: przywrócono jego przykładowy zapas i parametry.")
        st.button(
            "Przywróć parametry przykładowe",
            key="reset_parameters",
            on_click=reset_parameters,
            args=(st.session_state, defaults),
        )
        initial = st.number_input(
            "Zapas początkowy [szt.]",
            min_value=0,
            step=1,
            key="initial_stock",
            persist_state="session",
        )
        lead = st.number_input(
            "Czas dostawy [dni]",
            min_value=1,
            max_value=21,
            step=1,
            key="lead_time",
            persist_state="session",
        )
        review = st.number_input(
            "Przegląd co [dni]",
            min_value=1,
            max_value=7,
            step=1,
            key="review_period",
            persist_state="session",
        )
        buffer = st.number_input(
            "Bufor [szt.]", min_value=0, step=1, key="buffer", persist_state="session"
        )
        with st.expander("Hipotetyczne koszty"):
            holding = st.number_input(
                "Utrzymanie [GBP/szt./dzień]",
                min_value=0.0,
                step=0.01,
                key="holding",
                persist_state="session",
            )
            order = st.number_input(
                "Zamówienie [GBP/zam.]",
                min_value=0.0,
                step=1.0,
                key="order_cost",
                persist_state="session",
            )
            shortage = st.number_input(
                "Niedobór [GBP/szt.]",
                min_value=0.0,
                step=0.1,
                key="shortage",
                persist_state="session",
            )
        parameters = InventoryParameters(initial, lead, review, buffer, holding, order, shortage)
    with output:
        st.caption("28 dni · wspólna ścieżka sprzedaży dla wszystkich metod · koszty hipotetyczne")
        try:
            results = {
                m: simulate(
                    final[final.method == m].sort_values("horizon").prediction.to_numpy(),
                    sales,
                    parameters,
                )
                for m in methods
            }
        except ValueError as exc:
            st.error(f"Nieprawidłowe parametry symulacji: {exc}")
            return
        result = results[method]
        measures = [
            ("service_rate", "Udział obsłużonych sztuk", "%", 100),
            ("unserved_units", "Nieobsłużone sztuki", " szt.", 1),
            ("total_cost_gbp", "Koszt symulacji", " GBP", 1),
            ("ending_stock", "Zapas końcowy", " szt.", 1),
        ]
        baseline = st.session_state.get("baseline")
        for start in range(0, len(measures), 2):
            columns = st.columns(2)
            for column, (field, label, suffix, scale) in zip(
                columns, measures[start : start + 2], strict=True
            ):
                value = result.summary[field]
                delta = None
                if baseline and value is not None and baseline["summary"][field] is not None:
                    delta = display(
                        (value - baseline["summary"][field]) * scale,
                        " pp" if field == "service_rate" else suffix,
                        digits=measure_digits(field),
                    )
                column.metric(
                    label,
                    display(
                        None if value is None else value * scale,
                        suffix,
                        digits=measure_digits(field),
                    ),
                    delta=delta,
                    delta_color="off",
                    border=True,
                )
        st.plotly_chart(
            inventory_chart(result, reference.target_date, method),
            width="stretch",
            alt="Zsynchronizowane wykresy zapasu oraz zamówień, dostaw i niedoborów",
        )
        st.button(
            "Zapisz jako punkt odniesienia",
            key="save_baseline",
            on_click=lambda: st.session_state.update(
                baseline={
                    "context": context,
                    "parameters": parameters,
                    "summary": result.summary.copy(),
                    "result": result,
                }
            ),
        )
        if baseline:
            st.markdown("**A: zapisany punkt odniesienia · B: bieżący scenariusz**")
            changes = changed_parameters(baseline["parameters"], parameters)
            names = {
                "initial_stock": "Zapas początkowy",
                "lead_time_days": "Czas dostawy",
                "review_period_days": "Przegląd co",
                "safety_stock_units": "Bufor",
                "holding_cost": "Koszt utrzymania",
                "order_cost": "Koszt zamówienia",
                "shortage_penalty": "Koszt niedoboru",
            }
            st.caption(
                "; ".join(f"{names[k]}: {a} → {b}" for k, (a, b) in changes.items())
                or "Parametry A i B są identyczne."
            )
            comparison = pd.DataFrame(
                [
                    {
                        "Wynik": label,
                        "A": display(
                            baseline["summary"][field] * scale
                            if baseline["summary"][field] is not None
                            else None,
                            suffix,
                            digits=measure_digits(field),
                        ),
                        "B": display(
                            result.summary[field] * scale
                            if result.summary[field] is not None
                            else None,
                            suffix,
                            digits=measure_digits(field),
                        ),
                        "B − A": display(
                            (result.summary[field] - baseline["summary"][field]) * scale
                            if result.summary[field] is not None
                            and baseline["summary"][field] is not None
                            else None,
                            " pp" if field == "service_rate" else suffix,
                            digits=measure_digits(field),
                        ),
                    }
                    for field, label, suffix, scale in measures
                ]
            )
            show_table(comparison, hide_index=True, alt="Wyniki A i B oraz różnice")
        else:
            st.caption(
                "Zmiana produktu, metody, daty lub ścieżki sprzedaży usuwa punkt odniesienia A."
            )
        provenance = {
            "sku": sku,
            "origin": str(origin.date()),
            "method": method,
            "scenario": scenario,
            "multiplier": multiplier,
            "source_sha": data["manifest"]["source_sha"],
            "run_id": final[final.method == method].run_id.iloc[0],
        }
        with st.container(horizontal=True):
            st.download_button(
                "Scenariusz B · CSV",
                result.export_csv(provenance),
                f"inventory_{sku}_{method}.csv",
                "text/csv",
                key="inventory_csv",
            )
            st.download_button(
                "Scenariusz B · JSON",
                result.export_json(provenance),
                f"inventory_{sku}_{method}.json",
                "application/json",
                key="inventory_json",
            )
    with st.expander("Porównanie metod i szczegóły symulacji"):
        st.caption(
            "Wspólna ścieżka: historyczna sprzedaż albo prognoza metody domyślnej × mnożnik, floor(x+0,5). Przykładowy zapas = ceil(7 × średnia 28 dni historii). Sama zmiana dostawy nie zmienia zapasu początkowego."
        )
        show_table(
            pd.DataFrame(
                [
                    {
                        "Metoda": method_label(m),
                        "Obsługa [%]": display(
                            r.summary["service_rate"] * 100
                            if r.summary["service_rate"] is not None
                            else None
                        ),
                        "Niedobór [szt.]": display(r.summary["unserved_units"], digits=0),
                        "Koszt [GBP]": display(r.summary["total_cost_gbp"]),
                    }
                    for m, r in results.items()
                ]
            ),
            hide_index=True,
            alt="Metody na wspólnej ścieżce",
        )
        st.write(
            "Dostawy → przegląd i zamówienie → sprzedaż → koszty. Brak backorders i początkowego pipeline. Okno celu kończy się w dniu 28; brak wyceny odzysku zapasu. Wynik jest symulacją, nie optymalizacją rzeczywistej firmy."
        )
        st.json({"parameters": asdict(parameters), "provenance": provenance})
        daily_table = result.daily.copy()
        for col in daily_table.select_dtypes("number"):
            daily_table[col] = daily_table[col].map(
                lambda x, column=col: display(x, digits=2 if "cost" in column else 0)
            )
        show_table(daily_table, hide_index=True, alt="Pełny dzienny przebieg scenariusza B")


def frozen_report(root, name):
    path = root / "reports" / name
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path, dtype={"sku": str})
        key = "sku" if name == "metrics_by_sku.csv" else "horizon"
        required = {"split", "method", key, "mae", "wape", "bias"}
        if not required.issubset(frame.columns) or frame.empty:
            raise ValueError("Niekompletny schemat raportu")
        if frame.duplicated(["split", "method", key]).any():
            raise ValueError("Powtórzone grupy raportu")
        for _, group in frame.groupby(["split", key]):
            if set(group.method) != set(METHODS):
                raise ValueError("Niekompletne metody raportu")
        if key == "horizon":
            for _, group in frame.groupby(["split", "method"]):
                if sorted(group.horizon.tolist()) != list(range(1, 29)):
                    raise ValueError("Niekompletne 28 dni raportu")
        for column in ("mae", "wape", "bias"):
            if np.isinf(frame[column].to_numpy(dtype=float)).any():
                raise ValueError("Nieskończone wartości raportu")
        return frame
    except (OSError, ValueError, TypeError, KeyError):
        st.error(
            f"Niespójny zapisany raport {name}. Przywróć ten plik z kompletnej wersji projektu."
        )
        return pd.DataFrame()


def methods_view(data, root, sku, method, methods):
    stage = st.selectbox(
        "Etap oceny",
        ["validation", "final_test"],
        format_func=lambda s: (
            "Walidacja · wybór metody" if s == "validation" else "Test końcowy · zamrożony"
        ),
        key="evaluation_stage",
        persist_state="session",
    )
    metrics = data["metrics"]
    subset = (
        metrics[metrics.split.str.startswith("validation")]
        if stage == "validation"
        else metrics[metrics.split == "final_test"]
    )
    st.caption(
        f"Metryki globalne · wszystkie produkty. Wybrana na walidacji: {method_label(data['manifest']['winner'])}. WAPE to błąd: niżej = lepiej."
    )
    if subset.empty:
        st.info("Brak zapisanych metryk tego etapu.")
        return
    if subset.split.nunique() > 1:
        split = st.selectbox(
            "Zapisane okno walidacji", subset.split.unique().tolist(), key="validation_window"
        )
        subset = subset[subset.split == split]
    fig = go.Figure()
    for m in methods:
        f = subset[subset.method == m]
        if not f.empty:
            fig.add_bar(
                x=f.wape,
                y=[method_label(m)],
                name=method_label(m),
                orientation="h",
                marker_color=METHODS[m][1],
            )
    fig = style(fig, 210)
    fig.update_layout(showlegend=False, xaxis_title="WAPE [%] · niżej = lepiej", yaxis_title=None)
    st.plotly_chart(fig, width="stretch", alt="Globalny błąd WAPE trzech metod")
    columns = [c for c in ["mae", "wape", "bias"] if c in subset]
    table = method_table(subset, columns, formatted=True)
    table["Wybór"] = [
        "Wybrana na walidacji" if m == data["manifest"]["winner"] else "" for m in subset.method
    ]
    show_table(
        table,
        hide_index=True,
        alt="Globalne MAE, WAPE i bias; wybór walidacyjny oznaczony etykietą",
    )
    with st.expander("Pokrycie i szerokość przedziałów", expanded=True):
        bounds = pd.DataFrame(
            {
                "Metoda": subset.method.map(method_label),
                "Pokrycie 80%": subset.coverage80.map(lambda x: display(x * 100, "%")),
                "Szerokość 80%": subset.width80.map(lambda x: display(x, " szt.")),
                "Pokrycie 95%": subset.coverage95.map(lambda x: display(x * 100, "%")),
                "Szerokość 95%": subset.width95.map(lambda x: display(x, " szt.")),
            }
        )
        show_table(bounds, hide_index=True, alt="Pokrycie w procentach i szerokość w sztukach")
    st.caption(
        "MAE: średni błąd w sztukach. WAPE: suma błędów / suma sprzedaży [%]. Bias: kierunek względnego błędu [%]. N/A: brak wyniku lub przedziałów."
    )
    if stage == "validation":
        st.info(
            "Demo zawiera łączną ocenę czterech walidacji. Nie zawiera prognoz walidacyjnych ani łącznych wyników per produkt; nie pokazujemy tu danych testu końcowego."
        )
        with st.expander("Błędy według horyzontu · zapisane okna walidacji"):
            horizon = frozen_report(root, "metrics_by_horizon.csv")
            horizon_report_chart(
                horizon[horizon.split.str.startswith("validation")]
                if not horizon.empty
                else horizon
            )
        return
    st.subheader(f"Test · aktualny produkt {sku}")
    per_sku = frozen_report(root, "metrics_by_sku.csv")
    if not per_sku.empty:
        per_sku = per_sku[per_sku.split == "final_test"]
        show_table(
            method_table(per_sku[per_sku.sku == sku], ["mae", "wape", "bias"], formatted=True),
            hide_index=True,
            alt="Testowe metryki aktualnego produktu, oddzielone od globalnych",
        )
    else:
        st.info("Brak zapisanych metryk per produkt.")
    with st.expander("Test · błąd według horyzontu"):
        horizon = frozen_report(root, "metrics_by_horizon.csv")
        horizon_report_chart(
            horizon[horizon.split == "final_test"] if not horizon.empty else horizon
        )
    with st.expander("Test · trudne przypadki"):
        if not per_sku.empty:
            hard = (
                per_sku[per_sku.method == data["manifest"]["winner"]]
                .sort_values("mae", ascending=False)
                .head(8)
            )
            show_table(
                format_metrics(hard[["sku", "mae", "wape", "bias"]]).rename(
                    columns={
                        "sku": "SKU",
                        "mae": "MAE [szt.]",
                        "wape": "WAPE [%]",
                        "bias": "Bias [%]",
                    }
                ),
                hide_index=True,
                alt="Osiem największych błędów MAE domyślnej metody",
            )
            st.caption(
                "Duże zakupy i zanikanie sprzedaży utrudniają prognozę. Wyniki produktu mają tylko 28 obserwacji."
            )


def horizon_report_chart(frame):
    if frame.empty:
        st.info("Brak zapisanych wyników według horyzontu.")
        return
    fig = go.Figure()
    for (split, method), f in frame.groupby(["split", "method"]):
        fig.add_scatter(
            x=f.horizon,
            y=f.mae,
            name=f"{method_label(method)} · {split}",
            line=dict(color=METHODS[method][1], dash=METHODS[method][2]),
        )
    fig = style(fig, 310)
    fig.update_layout(xaxis_title="Horyzont [dni]", yaxis_title="MAE [szt.]")
    st.plotly_chart(fig, width="stretch", alt="Zapisany błąd według horyzontu i etapu")
