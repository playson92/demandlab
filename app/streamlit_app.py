"""Presentation entry point: read frozen artifacts and simulate inventory only."""

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from artifacts import ArtifactError, artifact_version, load_artifacts
from presentation import GROUPS, VIEWS, method_label
from views import inventory_view, methods_view, product_view

st.set_page_config(
    page_title="DemandLab · prognoza i zapas", page_icon=":material/query_stats:", layout="wide"
)
ROOT = Path(__file__).resolve().parents[1]
DEMO = Path(os.environ.get("DEMANDLAB_DEMO_DIR", str(ROOT / "data/demo")))


@st.cache_data(max_entries=3, show_spinner="Wczytywanie zapisanych danych demo…")
def cached_load(path, version):
    return load_artifacts(Path(path))


st.sidebar.title("DemandLab")
st.sidebar.caption("Historyczna sprzedaż → prognoza → zapas")
try:
    data = cached_load(str(DEMO), artifact_version(DEMO))
except ArtifactError as exc:
    st.title("DemandLab")
    st.error(str(exc), icon=":material/error:")
    st.caption(
        "Przywróć komplet data/demo z pobranej wersji repozytorium. Demo nie wymaga treningu ani lokalnych danych UCI."
    )
    st.stop()
products = data["products"]
manifest = data["manifest"]
origin = pd.Timestamp(manifest["test_origin"])
methods = [manifest["winner"]] + [
    m for m in data["forecasts"].method.unique() if m != manifest["winner"]
]
if "url_checked" not in st.session_state:
    # URLs use stable identifiers while widgets display readable labels. Accept
    # old display-label URLs too; validate before initializing shared state.
    url_labels = {
        "view": VIEWS,
        "sku": {
            s: f"{s} · {products.loc[products.sku == s, 'name'].iloc[0]}" for s in products.sku
        },
        "method": {m: method_label(m) for m in methods},
    }
    for key, labels in url_labels.items():
        incoming = st.query_params.get(key)
        if incoming in labels:
            st.session_state[key] = incoming

        elif incoming in labels.values():
            st.session_state[key] = next(k for k, v in labels.items() if v == incoming)
        elif incoming is not None:
            st.session_state["url_notice"] = (
                "Nieznany parametr adresu został pominięty. Wybrano dostępne ustawienia demo."
            )
    st.session_state["url_checked"] = True
view = st.sidebar.radio("Widok", list(VIEWS), format_func=VIEWS.get, key="view")
st.sidebar.caption(
    f"Data wystawienia prognozy\n\n**{origin:%d.%m.%Y}**\n\n80 produktów · 28 dni prognozy"
)
st.sidebar.caption("UCI Online Retail II · UK, 2009–2011. Koszty zapasu są hipotetyczne.")
if st.session_state.get("url_notice"):
    st.info(st.session_state.pop("url_notice"))
if view == "product":
    with st.container(horizontal=True):
        for group, example in manifest.get("examples", {}).items():
            st.button(
                f"Przykład: {GROUPS.get(group, group).lower()}",
                key=f"example_{group}",
                on_click=lambda s=example: st.session_state.update(sku=s),
            )
with st.container(horizontal=True, vertical_alignment="bottom"):
    sku = st.selectbox(
        "Wyszukaj produkt po nazwie lub SKU",
        products.sku.tolist(),
        format_func=lambda s: f"{s} · {products.loc[products.sku == s, 'name'].iloc[0]}",
        key="sku",
        width=450,
    )
    method = st.selectbox(
        "Metoda prognozy",
        methods,
        format_func=method_label,
        key="method",
        width=450,
    )
st.query_params.from_dict({"view": view, "sku": sku, "method": method})
row = products.loc[products.sku == sku].iloc[0]
st.subheader(row["name"])
st.caption(f"SKU {sku} · {GROUPS.get(row['group'], row['group'])} · {VIEWS[view]}")
history = data["daily"].query("sku == @sku and date <= @origin").sort_values("date")
final = data["forecasts"].query("sku == @sku and origin == @origin").sort_values("horizon")
observed = data["actuals"].query("sku == @sku").sort_values("date")
if view == "product":
    product_view(data, history, final, observed, origin, sku, method, methods)
elif view == "inventory":
    inventory_view(data, history, final, observed, origin, sku, method, methods)
else:
    methods_view(data, ROOT, sku, method, methods)
with st.expander("Metodologia, źródła i pochodzenie"):
    st.write(
        "Domyślną metodę wybrano na łącznym WAPE czterech walidacji; przewaga względna poniżej 1% preferuje prostszą metodę. Test nie zmienia wyboru. Wszystkie 28 dni wystawiono naraz; sprzedaż testowa nie aktualizuje prognozy."
    )
    st.write(
        "Sprzedaż zarejestrowana nie mierzy ukrytego popytu. Zera oznaczają brak sprzedaży przy założeniu kompletności źródła; nie znamy dostępności magazynowej."
    )
    st.write(
        "Nominalne przedziały empiryczne skalibrowano na dwóch wcześniejszych oknach. Ich pokrycie nie jest gwarancją dla konkretnego produktu."
    )
    st.markdown(
        "[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) · dokumentacja: docs/methodology.md i docs/frontend.md."
    )
    st.json(manifest)
    st.dataframe(
        final[["method", "origin", "run_id"]].drop_duplicates(),
        hide_index=True,
        alt="Techniczne identyfikatory zapisanych prognoz",
    )
    st.caption(
        "Adres przeglądarki odtwarza widok przy uruchomionej aplikacji. Lokalny adres nie jest publicznym serwisem."
    )
