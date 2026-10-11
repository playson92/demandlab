"""Polish portfolio dashboard backed exclusively by versioned UCI artifacts."""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from artifacts import ArtifactError, artifact_version, load_artifacts

from demandlab.inventory import InventoryParameters, simulate

st.set_page_config(
    page_title="DemandLab · prognoza i zapas", page_icon=":material/query_stats:", layout="wide"
)

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path(os.environ.get("DEMANDLAB_DEMO_DIR", str(ROOT / "data/demo")))
COLORS = ["#14b8a6", "#648cff", "#f4a261"]


@st.cache_data(max_entries=3)
def cached_load(path, version):
    return load_artifacts(Path(path))


def display(value, suffix="", digits=2):
    return (
        "N/A"
        if value is None or pd.isna(value)
        else f"{value:,.{digits}f}".replace(",", " ").replace(".", ",") + suffix
    )


def chart_style(fig):
    fig.update_layout(
        height=400,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.12),
        hovermode="x unified",
        xaxis_title="Data",
        yaxis_title="Sztuki",
        font=dict(size=13),
    )
    return fig


st.sidebar.title("DemandLab")
st.sidebar.caption("Od sprzedaży do decyzji o zapasie")
view = st.sidebar.radio(
    "Widok", ["Przegląd", "Prognoza produktu", "Jakość modeli", "Symulator"], key="view"
)
try:
    data = cached_load(str(DEMO), artifact_version(DEMO))
except ArtifactError as exc:
    st.title("DemandLab")
    st.error(str(exc), icon=":material/error:")
    st.caption(
        "Demo korzysta wyłącznie z zapisanych agregatów UCI. Nie pobiera danych ani nie uruchamia treningu."
    )
    st.stop()

products, forecasts, daily, actuals = (
    data[name] for name in ("products", "forecasts", "daily", "actuals")
)
manifest = data["manifest"]
origin = pd.Timestamp(manifest["test_origin"])
labels = dict(zip(products.sku, products.sku + " · " + products.name, strict=False))
sku = st.sidebar.selectbox(
    "Produkt · kod i nazwa", products.sku.tolist(), format_func=lambda x: labels[x], key="sku"
)
winner = manifest["winner"]
methods = list(forecasts.method.unique())
methods = [winner] + [m for m in methods if m != winner]
st.sidebar.caption(f"Historyczny origin: {origin:%d.%m.%Y}\n\nŹródło: UCI Online Retail II · UK")
st.sidebar.caption("Nominalne przedziały empiryczne nie gwarantują pokrycia konkretnego produktu.")
history = daily[(daily.sku == sku) & (daily.date <= origin)].sort_values("date")
final = forecasts[(forecasts.sku == sku) & (forecasts.origin == origin)].sort_values("horizon")
observed = actuals[actuals.sku == sku].sort_values("date")
if final.empty:
    st.warning("Brak wyniku dla wybranego produktu i originu.")
    st.stop()
st.caption("PORTFOLIO / DATA SCIENCE / UCI 2009–2011")
st.title(view)
st.caption(
    "Zarejestrowana sprzedaż historyczna. Wyniki nie są prognozą bieżącego handlu ani pomiarem ukrytego popytu."
)

if view == "Przegląd":
    st.markdown("### Prognoza ma sens, kiedy prowadzi do czytelnej decyzji")
    st.markdown(
        "Porównujemy dwie proste metody i globalny model drzewiasty. Zamrożona prognoza 28 dni zasila symulację uzupełniania zapasu; rzeczywista sprzedaż służy do oceny po jej zapisaniu."
    )
    metric = data["metrics"].query("split == 'final_test' and method == @winner")
    with st.container(horizontal=True):
        st.metric("Produkty", str(len(products)), border=True)
        st.metric("Horyzont", "28 dni", border=True)
        st.metric(
            "Test · WAPE", display(metric.wape.iloc[0] if len(metric) else None, "%"), border=True
        )
        st.metric(
            "Test · MAE", display(metric.mae.iloc[0] if len(metric) else None, " szt."), border=True
        )
    st.caption(
        f"Zakres agregatów: {daily.date.min():%d.%m.%Y} – {daily.date.max():%d.%m.%Y}. Domyślna metoda: {winner}."
    )
    with st.container(border=True):
        st.subheader(labels[sku])
        fig = px.line(history.tail(180), x="date", y="y", color_discrete_sequence=COLORS)
        st.plotly_chart(
            chart_style(fig),
            width="stretch",
            alt="Zarejestrowana sprzedaż wybranego produktu przed originem",
        )
        if history.y.sum() == 0:
            st.info("Produkt nie ma dodatniej zarejestrowanej sprzedaży w dostępnej historii.")
    st.subheader("Dwa profile sprzedaży")
    st.caption(
        "Przykłady wybrano według największej liczby sztuk w grupach w początkowych 365 dniach; remisy rozstrzyga kod SKU. Nie korzystamy z wyników testu."
    )
    if manifest.get("examples"):
        examples = products[products.sku.isin(manifest["examples"].values())]
    elif "initial_units" in products:
        examples = (
            products.sort_values(["initial_units", "sku"], ascending=[False, True])
            .groupby("group", sort=True)
            .head(1)
        )
    else:
        examples = products.sort_values("sku").groupby("group", sort=True).head(1)
    for col, row in zip(st.columns(max(1, len(examples))), examples.itertuples(), strict=False):
        with col.container(border=True):
            st.markdown(f"**{row.group} · {row.sku}**")
            frame = daily[(daily.sku == row.sku) & (daily.date <= origin)].tail(84)
            st.line_chart(
                frame.set_index("date")["y"], height=180, alt=f"Przedtestowy profil SKU {row.sku}"
            )
    st.caption(
        "Zera oznaczają brak zarejestrowanej sprzedaży przy założeniu kompletności źródła. Nie znamy dostępności magazynowej ani utraconego popytu."
    )

elif view == "Prognoza produktu":
    st.subheader(labels[sku])
    selected = st.multiselect("Metody", methods, default=methods, key="forecast_methods")
    interval = st.selectbox("Przedział nominalny", ["80%", "95%", "Brak"], key="interval")
    show_actual = st.toggle("Pokaż sprzedaż z testu", value=True)
    fig = go.Figure()
    fig.add_scatter(
        x=history.tail(84).date, y=history.tail(84).y, name="Historia", line=dict(color="#9ca3af")
    )
    for method in selected:
        f = final[final.method == method]
        color = COLORS[methods.index(method) % len(COLORS)]
        if interval != "Brak":
            low, high = ("q10", "q90") if interval == "80%" else ("q025", "q975")
            if f[[low, high]].notna().all().all():
                fig.add_scatter(
                    x=f.target_date,
                    y=f[low],
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
                fig.add_scatter(
                    x=f.target_date,
                    y=f[high],
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(20,184,166,0.12)",
                    name=f"{method} · {interval}",
                )
            else:
                st.caption(f"{method}: przedziały nie są dostępne dla tego originu.")
        fig.add_scatter(
            x=f.target_date, y=f.prediction, name=method, line=dict(color=color, width=2)
        )
    if show_actual:
        fig.add_scatter(
            x=observed.date,
            y=observed.y,
            name="Sprzedaż testowa",
            line=dict(color="#ffffff", dash="dot"),
        )
    fig.add_vline(x=origin.timestamp() * 1000, line_dash="dash", line_color="#f4a261")
    fig.add_annotation(x=origin, y=1, yref="paper", text="Origin", showarrow=False, xanchor="right")
    st.plotly_chart(
        chart_style(fig),
        width="stretch",
        alt="Historia, origin, prognozy i nominalne przedziały dla kolejnych 28 dni",
    )
    st.caption(
        f"Wiedza prognozy kończy się {origin:%d.%m.%Y}. Całe 28 dni wystawiono naraz; sprzedaż z testu nie aktualizuje prognoz. Przedziały skalibrowano wyłącznie na dwóch wcześniejszych oknach."
    )
    table = final[final.method.isin(selected)]
    st.download_button(
        "Pobierz prognozę · CSV",
        table.to_csv(index=False),
        f"forecast_{sku}.csv",
        "text/csv",
        icon=":material/download:",
    )
    with st.expander("Tabela i pochodzenie prognozy"):
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            alt="Zapisane prognozy i identyfikatory eksperymentów",
        )
        st.json(
            {"origin": str(origin.date()), "source_sha": manifest["source_sha"], "winner": winner}
        )

elif view == "Jakość modeli":
    stage = st.selectbox(
        "Etap oceny",
        ["Walidacja · wybór metody", "Test końcowy · zamrożony"],
        key="evaluation_stage",
    )
    metrics = data["metrics"]
    subset = (
        metrics[metrics.split.str.startswith("validation")]
        if stage.startswith("Walidacja")
        else metrics[metrics.split == "final_test"]
    )
    st.caption(
        f"Metodę {winner} wybrano globalnie po łącznym WAPE czterech walidacji. Względna przewaga poniżej 1% preferuje prostszą metodę. Wynik testu nie zmienia zwycięzcy."
    )
    if subset.empty:
        st.info("Brak zapisanych metryk dla wybranego etapu.")
    else:
        fig = px.bar(
            subset,
            x="method",
            y="wape",
            color="method",
            facet_col="split" if subset.split.nunique() > 1 else None,
            color_discrete_sequence=COLORS,
        )
        fig.update_layout(
            height=300, showlegend=False, yaxis_title="WAPE [%]", xaxis_title="Metoda"
        )
        st.plotly_chart(fig, width="stretch", alt="Porównanie WAPE metod na tych samych oknach")
        st.dataframe(
            subset,
            hide_index=True,
            width="stretch",
            alt="MAE, WAPE, nominalne pokrycie i szerokość przedziałów",
            column_config={
                "method": "Metoda",
                "split": "Okno oceny",
                "mae": "MAE [szt.]",
                "wape": "WAPE [%]",
                "coverage80": st.column_config.NumberColumn("Pokrycie 80%", format="%.3f"),
                "width80": "Szerokość 80% [szt.]",
                "coverage95": st.column_config.NumberColumn("Pokrycie 95%", format="%.3f"),
                "width95": "Szerokość 95% [szt.]",
                "bias": "Bias · prognoza−sprzedaż [%]",
            },
        )
    st.caption(
        "MAE i szerokość: sztuki. WAPE: %. Pokrycie: udział 0–1. N/A oznacza nieokreślony wynik; przedziały wcześniejszych walidacji są niedostępne."
    )
    joined = final.merge(
        observed.rename(columns={"date": "target_date"}), on=["sku", "target_date"], how="inner"
    )
    if not joined.empty:
        joined["absolute_error"] = (joined.prediction - joined.y).abs()
        st.subheader("Test · błąd według horyzontu wybranego produktu")
        fig = px.line(
            joined, x="horizon", y="absolute_error", color="method", color_discrete_sequence=COLORS
        )
        fig.update_layout(
            height=280, xaxis_title="Horyzont [dni]", yaxis_title="Błąd bezwzględny [szt.]"
        )
        st.plotly_chart(fig, width="stretch", alt="Błąd bezwzględny metod według horyzontu")
    st.subheader("Test · produkty i trudne przypadki")
    all_test = forecasts[forecasts.origin == origin].merge(
        actuals.rename(columns={"date": "target_date"}), on=["sku", "target_date"]
    )
    if not all_test.empty:
        all_test["absolute_error"] = (all_test.prediction - all_test.y).abs()
        by_sku = (
            all_test.groupby(["sku", "method"])
            .agg(
                mae=("absolute_error", "mean"),
                error_sum=("absolute_error", "sum"),
                sales=("y", "sum"),
            )
            .reset_index()
        )
        by_sku["wape"] = np.where(by_sku.sales > 0, 100 * by_sku.error_sum / by_sku.sales, np.nan)
        st.dataframe(
            by_sku.sort_values("mae", ascending=False),
            hide_index=True,
            height=230,
            alt="Rzeczywiste błędy produktów, z najtrudniejszymi przypadkami na początku",
        )
    st.caption(
        "Duże jednorazowe zakupy i zanik aktywności utrudniają prognozowanie. Wyniki per SKU mają mało obserwacji; wspólny wynik nie opisuje każdego produktu."
    )

elif view == "Symulator":
    st.subheader(labels[sku])
    st.caption(
        "Symulacja hipotetycznego magazynu na 28 dni. Dostawy → przegląd i zamówienie → sprzedaż → koszty. Brak backorders i początkowych dostaw w drodze."
    )
    scenario = st.selectbox(
        "Scenariusz",
        ["Historyczny · sprzedaż z testu", "Hipotetyczny · wspólna referencja"],
        key="scenario",
    )
    reference = final[final.method == winner].sort_values("horizon")
    if scenario.startswith("Historyczny"):
        aligned = reference[["target_date"]].merge(
            observed.rename(columns={"date": "target_date"}), on="target_date", how="left"
        )
        if aligned.y.isna().any():
            st.error(
                "Brakuje pełnej 28-dniowej ścieżki sprzedaży. Historyczna symulacja jest niedostępna."
            )
            st.stop()
        sales = aligned.y.to_numpy()
        multiplier = 1.0
        rule = "Recorded historical integer sales, shared by every method"
    else:
        multiplier = st.slider("Mnożnik wspólnej referencji", 0.0, 2.0, 1.0, 0.1, key="multiplier")
        sales = np.floor(reference.prediction.to_numpy() * multiplier + 0.5)
        rule = f"Winner forecast ({winner}) × {multiplier}; round half up to integer units"
        st.caption(
            "Referencja: prognoza domyślnej metody × mnożnik; zaokrąglenie floor(x+0,5). Każda metoda realizuje tę samą ścieżkę. To scenariusz, a nie niezależny test jakości."
        )
    default_stock = int(np.ceil(history.tail(28).y.mean() * 7)) if len(history) else 0
    with st.container(border=True):
        columns = st.columns(4)
        initial = columns[0].number_input(
            "Zapas początkowy [szt.]", min_value=0, value=default_stock, step=1, key="initial_stock"
        )
        lead = columns[1].number_input(
            "Czas dostawy [dni]", min_value=1, max_value=21, value=7, step=1, key="lead_time"
        )
        review = columns[2].number_input(
            "Przegląd co [dni]", min_value=1, max_value=7, value=7, step=1, key="review_period"
        )
        buffer = columns[3].number_input("Bufor [szt.]", min_value=0, value=0, step=1, key="buffer")
        columns = st.columns(3)
        holding = columns[0].number_input(
            "Utrzymanie [GBP/szt./dzień]", min_value=0.0, value=0.01, step=0.01, key="holding"
        )
        order_cost = columns[1].number_input(
            "Zamówienie [GBP/zam.]", min_value=0.0, value=5.0, step=1.0, key="order_cost"
        )
        shortage = columns[2].number_input(
            "Niedobór [GBP/szt.]", min_value=0.0, value=1.0, step=0.1, key="shortage"
        )
    st.caption(
        "Początkowy przykład zapasu = ceil(7 × średnia ostatnich 28 dni przed originem). Zmiana czasu dostawy nie zmienia automatycznie zapasu. Koszty są hipotetyczne i nie sterują polityką."
    )
    parameters = InventoryParameters(initial, lead, review, buffer, holding, order_cost, shortage)
    try:
        results = {
            method: simulate(
                final[final.method == method].sort_values("horizon").prediction.to_numpy(),
                sales,
                parameters,
            )
            for method in methods
        }
    except ValueError as exc:
        st.error(f"Nieprawidłowe parametry symulacji: {exc}")
        st.stop()
    method = st.selectbox("Metoda · szczegóły", methods, key="simulation_method")
    result = results[method]
    with st.container(horizontal=True):
        st.metric(
            "Obsłużone sztuki",
            display(
                None
                if result.summary["service_rate"] is None
                else 100 * result.summary["service_rate"],
                "%",
            ),
            border=True,
        )
        st.metric("Nieobsłużone sztuki", str(result.summary["unserved_units"]), border=True)
        st.metric("Koszt symulacji", display(result.summary["total_cost_gbp"], " GBP"), border=True)
        st.metric("Zapas końcowy", str(result.summary["ending_stock"]), border=True)
    f = result.daily
    fig = go.Figure()
    fig.add_scatter(
        x=f.day, y=f.ending_stock, name="Zapas końcowy", line=dict(color=COLORS[0]), fill="tozeroy"
    )
    for name, label, color in [
        ("ordered", "Zamówienia", COLORS[1]),
        ("received", "Dostawy", "#d6dce8"),
        ("unserved", "Nieobsłużone", COLORS[2]),
    ]:
        fig.add_bar(x=f.day, y=f[name], name=label, marker_color=color, opacity=0.7)
    fig = chart_style(fig)
    fig.update_layout(xaxis_title="Dzień symulacji", barmode="group", height=320)
    st.plotly_chart(
        fig,
        width="stretch",
        alt="Dzienne stany magazynu, zamówienia, dostawy i nieobsłużona sprzedaż",
    )
    st.caption(
        "Cel S = ceil(suma prognoz od d do min(28,d+L+R−1) + bufor). Q = max(0,S−zapas−pipeline). Zamówienie dociera rano d+L, tylko do dnia 28. Skrócenie końcowego okna wpływa na wynik; nie wyceniamy odzysku zapasu."
    )
    comparison = pd.DataFrame([{"method": m, **r.summary} for m, r in results.items()])
    st.dataframe(
        comparison,
        hide_index=True,
        width="stretch",
        alt="Porównanie wskaźników obsługi, zapasu i hipotetycznych kosztów metod",
        column_config={
            "method": "Metoda",
            "service_rate": "Obsłużone / sprzedaż",
            "unserved_units": "Nieobsłużone [szt.]",
            "shortage_days": "Dni z niedoborem",
            "mean_stock": "Średni zapas [szt.]",
            "ending_stock": "Zapas końcowy [szt.]",
            "pipeline_units": "W drodze [szt.]",
            "orders": "Zamówienia",
            "ordered_units": "Zamówione [szt.]",
            "received_units": "Przyjęte [szt.]",
            "holding_cost_gbp": "Utrzymanie [GBP]",
            "order_cost_gbp": "Zamówienia [GBP]",
            "shortage_cost_gbp": "Niedobór [GBP]",
            "total_cost_gbp": "Suma [GBP]",
        },
    )
    provenance = {
        "sku": sku,
        "origin": str(origin.date()),
        "method": method,
        "run_id": str(final[final.method == method].run_id.iloc[0]),
        "source_sha": manifest["source_sha"],
        "scenario": scenario,
        "scenario_rule": rule,
    }
    with st.container(horizontal=True):
        st.download_button(
            "Eksport dzienny · CSV",
            result.export_csv(provenance),
            f"inventory_{sku}.csv",
            "text/csv",
            icon=":material/download:",
        )
        st.download_button(
            "Eksport z parametrami · JSON",
            result.export_json(provenance),
            f"inventory_{sku}.json",
            "application/json",
            icon=":material/download:",
        )
    with st.expander("Dzienny bilans i koszty"):
        st.dataframe(f, hide_index=True, width="stretch", alt="Dzienne zdarzenia i saldo magazynu")
    st.caption(
        "Nie znamy historycznych stanów magazynu. Sprzedaż zarejestrowana nie mierzy całego popytu. Bufor nie ma gwarantowanego poziomu obsługi; symulator nie optymalizuje kosztów ani nie obiecuje oszczędności."
    )
