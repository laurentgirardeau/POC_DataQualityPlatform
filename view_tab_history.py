# ======================================================================================
# view_tab_history.py — Onglet 📋 History (Detailed View)
#
# Lazy loading: all SQL queries execute only when this tab is active.
# Contains: filters, period KPIs, trend line chart, DMF×Hour heatmap,
#           execution log table, CSV export button.
# ======================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from snowflake.snowpark import Session

from config import CHART_FONT_COLOR, CHART_GRID_COLOR, CHART_BG, CHART_PLOT_BG
from queries import get_table_execution_history, get_table_dmf_trend
from components import cast_numeric, render_kpi_card, render_dimension_scores


def render_tab_history(
    session: Session,
    db: str,
    schema: str,
    table: str,
    time_window: int,
    last_ts,
    dim_scores: dict | None = None,
) -> None:
    """
    History tab content — full lazy load.
    Queries execute only when this tab is active (Streamlit tab lazy evaluation).
    """
    # ── Data load ─────────────────────────────────────────────────────────────
    history_df = get_table_execution_history(session, db, schema, table)
    trend_df   = get_table_dmf_trend(session, db, schema, table, hours=time_window)

    if history_df.empty:
        st.warning("No execution history available.")
        return

    # Normalize
    history_df.columns = [c.upper() for c in history_df.columns]
    history_df["MEASUREMENT_TIME"] = pd.to_datetime(history_df["MEASUREMENT_TIME"])
    history_df["VALUE"] = pd.to_numeric(history_df["VALUE"], errors="coerce").fillna(0)

    # ── Filters ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Filters</div>', unsafe_allow_html=True)
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    all_dmfs = sorted(history_df["METRIC_NAME"].unique().tolist())

    with col_f1:
        selected_dmfs = st.multiselect(
            "Filter by DMF",
            options=all_dmfs, default=all_dmfs,
            key="hist_dmf_filter",
        )
    with col_f2:
        status_filter = st.multiselect(
            "Filter by Status",
            options=["PASSED", "FAILED", "NO_DATA"],
            default=["PASSED", "FAILED", "NO_DATA"],
            key="hist_status_filter",
        )
    with col_f3:
        show_zero = st.toggle("Show VALUE=0", value=True, key="hist_show_zero")

    filt_df = history_df[history_df["METRIC_NAME"].isin(selected_dmfs)].copy()
    filt_df = filt_df[filt_df["STATUS"].isin(status_filter)]
    if not show_zero:
        filt_df = filt_df[filt_df["VALUE"] > 0]

    # ── Period summary KPIs ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Period Summary</div>', unsafe_allow_html=True)
    failed_count = int((filt_df["STATUS"] == "FAILED").sum())
    fail_rate    = (filt_df["STATUS"] == "FAILED").mean() * 100 if len(filt_df) > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    with m1: render_kpi_card("Executions",    str(len(filt_df)),                     color="#1565c0")
    with m2: render_kpi_card("DMFs Analyzed", str(filt_df["METRIC_NAME"].nunique()),  color="#1565c0")
    with m3: render_kpi_card("Failures",      str(failed_count),                     color="#c62828")
    with m4:
        render_kpi_card(
            "Failure Rate", f"{fail_rate:.1f}%",
            color="#c62828" if fail_rate > 20 else "#e65100" if fail_rate > 5 else "#2e7d32",
        )

    # ── Dimension scores — current state of the table (from pre-tab load) ─────
    if dim_scores:
        render_dimension_scores(dim_scores)

    st.markdown("")

    # ── Trend chart ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Anomaly Trend Over Time</div>', unsafe_allow_html=True)

    if not trend_df.empty:
        trend_df.columns = [c.upper() for c in trend_df.columns]
        trend_df["MEASUREMENT_HOUR"] = pd.to_datetime(trend_df["MEASUREMENT_HOUR"])
        trend_df = cast_numeric(trend_df, ["AVG_VALUE", "MAX_VALUE", "MEASUREMENT_COUNT"])
        trend_filt = trend_df[trend_df["METRIC_NAME"].isin(selected_dmfs)]

        fig_line = px.line(
            trend_filt, x="MEASUREMENT_HOUR", y="AVG_VALUE", color="METRIC_NAME",
            markers=True,
            color_discrete_sequence=["#1565c0","#42a5f5","#2e7d32","#e65100","#7b1fa2","#00838f"],
            labels={"MEASUREMENT_HOUR": "Hour", "AVG_VALUE": "Avg value", "METRIC_NAME": "DMF"},
        )
        fig_line.update_layout(
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_PLOT_BG,
            font={"color": CHART_FONT_COLOR}, height=320,
            margin=dict(t=10, b=10, l=0, r=0),
            legend=dict(
                font=dict(color=CHART_FONT_COLOR),
                bgcolor="rgba(255,255,255,.8)",
                bordercolor=CHART_GRID_COLOR, borderwidth=1,
            ),
            xaxis=dict(showgrid=True, gridcolor=CHART_GRID_COLOR),
            yaxis=dict(showgrid=True, gridcolor=CHART_GRID_COLOR, title="Value"),
            hovermode="x unified",
        )
        fig_line.add_hline(y=0, line_color="#2e7d32", line_dash="dot", line_width=1.5, opacity=0.6)
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Not enough data in the selected window to display the trend.")

    # ── Heatmap (only when multiple DMFs present) ─────────────────────────────
    if not trend_df.empty and trend_df["METRIC_NAME"].nunique() > 1:
        st.markdown('<div class="section-title">Anomaly Heatmap (DMF × Hour)</div>', unsafe_allow_html=True)
        trend_filt = trend_df[trend_df["METRIC_NAME"].isin(selected_dmfs)]
        pivot = trend_filt.pivot_table(
            index="METRIC_NAME", columns="MEASUREMENT_HOUR",
            values="AVG_VALUE", aggfunc="mean",
        )
        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[str(c)[:16] for c in pivot.columns],
            y=pivot.index.tolist(),
            colorscale=[[0, "#e8f5e9"], [0.5, "#fff3e0"], [1, "#ffebee"]],
            text=pivot.values.round(1), texttemplate="%{text}",
            textfont={"color": CHART_FONT_COLOR},
            hovertemplate="DMF: %{y}<br>Hour: %{x}<br>Value: %{z:.1f}<extra></extra>",
            showscale=True, colorbar=dict(tickfont=dict(color=CHART_FONT_COLOR)),
        ))
        fig_heat.update_layout(
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_PLOT_BG,
            font={"color": CHART_FONT_COLOR},
            height=max(200, len(pivot) * 50 + 80),
            margin=dict(t=10, b=60, l=0, r=0),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, color=CHART_FONT_COLOR), automargin=True),
            yaxis=dict(tickfont=dict(color=CHART_FONT_COLOR), automargin=True),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    # ── Execution log table ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Execution Log</div>', unsafe_allow_html=True)

    cols = ["MEASUREMENT_TIME", "METRIC_NAME", "VALUE", "STATUS"]
    if "EXPECTATION_EXPRESSION" in filt_df.columns:
        cols.append("EXPECTATION_EXPRESSION")

    display_hist = filt_df[cols].copy()
    display_hist["MEASUREMENT_TIME"] = display_hist["MEASUREMENT_TIME"].dt.strftime("%Y-%m-%d %H:%M:%S")
    display_hist = display_hist.rename(columns={
        "MEASUREMENT_TIME":       "Timestamp",
        "METRIC_NAME":            "DMF Function",
        "VALUE":                  "Value",
        "STATUS":                 "Status",
        "EXPECTATION_EXPRESSION": "Evaluated Rule",
    })

    def _highlight_failed(row):
        return ["background-color:#fff0f0"] * len(row) if row["Status"] == "FAILED" else [""] * len(row)

    styled = (
        display_hist.style
        .apply(_highlight_failed, axis=1)
        .format({"Value": "{:.0f}"})
        .set_properties(**{"color": CHART_FONT_COLOR, "font-size": "0.85rem", "white-space": "nowrap"})
    )
    st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

    # ── CSV export ────────────────────────────────────────────────────────────
    col_dl, _ = st.columns([1, 3])
    with col_dl:
        csv_data = display_hist.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️  Export to CSV",
            data=csv_data,
            file_name=f"dmf_history_{table}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    if pd.notna(last_ts):
        st.caption(f"Source: `VW_DQ_ENRICHED_RESULTS` · Last measurement: {last_ts}")