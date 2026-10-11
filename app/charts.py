"""Public Plotly chart configuration using shared labels and colors."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from presentation import METHODS, method_label


def style(fig, height=330):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=45, b=12),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Arial, sans-serif", color="#29332E", size=12),
        legend=dict(orientation="h", y=1.18, font=dict(size=11)),
        hovermode="x unified",
        xaxis_title="Data",
        yaxis_title="Sztuki",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E8E8E1", rangemode="tozero")
    return fig


def forecast_chart(history, final, observed, origin, selected, band_method, interval, show_actual):
    fig = go.Figure()
    fig.add_scatter(
        x=history.date,
        y=history.y,
        name="Sprzedaż historyczna",
        line=dict(color="#637168", width=2),
    )
    if interval != "Brak":
        f = final[final.method == band_method]
        low, high = ("q10", "q90") if interval == "80%" else ("q025", "q975")
        if f[[low, high]].notna().all().all():
            color = METHODS[band_method][1]
            rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
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
                fillcolor=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.16)",
                name=f"Przedział {interval}",
            )
    for method in selected:
        f = final[final.method == method]
        fig.add_scatter(
            x=f.target_date,
            y=f.prediction,
            name=method_label(method),
            line=dict(color=METHODS[method][1], dash=METHODS[method][2], width=2.5),
        )
    if show_actual:
        fig.add_scatter(
            x=observed.date,
            y=observed.y,
            name="Sprzedaż testowa",
            line=dict(color="#252D29", dash="dash", width=2),
        )
    fig.add_vline(x=origin.timestamp() * 1000, line_color="#637168", line_dash="dash")
    fig.add_annotation(
        x=origin,
        y=0.55,
        yref="paper",
        text="Granica wiedzy",
        showarrow=False,
        xanchor="left",
        bgcolor="rgba(255,255,255,0.9)",
    )
    fig.update_xaxes(tickformat="%d.%m.%Y")
    return style(fig, 350)


def inventory_chart(result, dates, method):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.58, 0.42],
        subplot_titles=["Zapas na koniec dnia", "Zamówienia, dostawy i niedobory"],
    )
    f = result.daily
    fig.add_scatter(
        x=dates,
        y=f.ending_stock,
        name="Zapas",
        fill="tozeroy",
        line=dict(color=METHODS[method][1]),
        row=1,
        col=1,
    )
    for field, label, color, pattern in [
        ("ordered", "Zamówienie", "#5264A1", "/"),
        ("received", "Dostawa", "#247452", ""),
        ("unserved", "Niedobór", "#A34838", "x"),
    ]:
        fig.add_bar(
            x=dates,
            y=f[field],
            name=label,
            marker_color=color,
            marker_pattern_shape=pattern,
            row=2,
            col=1,
        )
    fig = style(fig, 360)
    fig.update_layout(barmode="group", xaxis_title=None, xaxis2_title="Data")
    fig.update_xaxes(tickformat="%d.%m")
    fig.update_yaxes(title_text="Sztuki", row=2, col=1)
    return fig
