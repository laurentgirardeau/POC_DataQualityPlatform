# ======================================================================================
# view_tab_summary.py — Onglet 📊 Summary (Detailed View)
#
# Receives latest_df_pre and pre-computed KPI scalars from view_detailed.py.
# No additional SQL queries — all data is already loaded.
# ======================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import CHART_FONT_COLOR, CHART_GRID_COLOR, CHART_BG, CHART_PLOT_BG
from components import (
    _strip_html,
    render_kpi_card,
    render_gauge,
    render_status_badge,
    render_type_badge,
    status_to_color,
    score_color,
    compute_dimension_scores,
    render_dimension_scores,
    _DIM_STYLE,
)


def render_tab_summary(
    score: float,
    sc: str,
    total: int,
    passed: int,
    failed: int,
    last_ts,
    latest_df: pd.DataFrame,
    dim_scores: dict | None = None,
) -> None:
    """
    Summary tab content:
      - 4 KPI cards
      - Quality gauge
      - DMF status table (CORE/CUSTOM badges, Rule, Value, Status)
      - Status distribution pie + Value by DMF bar chart
    """
    # ── KPI cards ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi_card("Quality Score",   f"{score:.1f}%", color=sc)
    with c2: render_kpi_card("Configured DMFs", str(total),       color="#1565c0")
    with c3: render_kpi_card("Passed Checks",   str(passed),      color="#2e7d32")
    with c4: render_kpi_card("Failed Checks",   str(failed),      color="#c62828")

    # ── Dimension scores — inline under KPI cards ─────────────────────────────
    # dim_scores pre-computed in view_detailed.py from enriched latest_df_pre
    _dim_scores = dim_scores if dim_scores is not None else compute_dimension_scores(latest_df)
    render_dimension_scores(_dim_scores)

    st.markdown("")

    # ── Quality gauge ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Overall Quality Score</div>', unsafe_allow_html=True)
    render_gauge(score, sc)

    # ── DMF status table ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Current DMF Status</div>', unsafe_allow_html=True)

    if latest_df.empty:
        st.info("No DMF results available.")
        return

    display_df = latest_df.copy()
    display_df["LAST_CHECKED"] = (
        pd.to_datetime(display_df["LAST_CHECKED"], errors="coerce")
        .dt.strftime("%Y-%m-%d %H:%M")
        .fillna("—")
    )
    display_df["ISSUES_FOUND"] = pd.to_numeric(display_df["ISSUES_FOUND"], errors="coerce")

    # DISPLAY_NAME: busname if tagged, raw DMF_NAME otherwise
    if "DISPLAY_NAME" not in display_df.columns:
        display_df["DISPLAY_NAME"] = display_df["DMF_NAME"]

    html_rows = ""
    for _, r in display_df.iterrows():
        is_nd        = pd.isna(r["ISSUES_FOUND"])
        issues_val   = "—" if is_nd else int(r["ISSUES_FOUND"])
        value_color  = status_to_color(r["STATUS"])
        dmf_rule     = str(r.get("DMF_RULE", "")) or "—"
        dim_raw      = str(r.get("DQ_DIMENSION", "") or "").upper()
        dim_bg, dim_fg, dim_border = _DIM_STYLE.get(dim_raw, ("#f5f5f5", "#616161", "#bdbdbd"))
        dim_label    = dim_raw.capitalize() if dim_raw else "—"
        dim_cell     = (
            f'<span style="background:{dim_bg};color:{dim_fg};border:1px solid {dim_border};'
            f'padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:700;'
            f'white-space:nowrap">{dim_label}</span>'
            if dim_raw else "—"
        )
        # Column reference: shown when the same DMF is on multiple columns (Bug 2 fix)
        col_ref = str(r.get("REF_COLUMN_NAME") or "").strip()
        col_cell = (
            f'<span style="font-family:Consolas,monospace;font-size:.78rem;'
            f'color:#5a7290;background:#f0f5fb;padding:1px 6px;border-radius:4px">'
            f'{col_ref}</span>'
            if col_ref else '<span style="color:#c8d8ec">—</span>'
        )
        html_rows += (
            f'<tr>'
            f'<td style="font-weight:500" title="{r["DMF_NAME"]}">{r["DISPLAY_NAME"]}</td>'
            f'<td style="text-align:center">{render_type_badge(r["DMF_TYPE"])}</td>'
            f'<td style="text-align:center">{dim_cell}</td>'
            f'<td style="text-align:center">{col_cell}</td>'
            f'<td style="color:#5a7290;font-size:.82rem">{dmf_rule}</td>'
            f'<td style="text-align:center;color:{value_color};font-weight:700">{issues_val}</td>'
            f'<td style="text-align:center">{render_status_badge(r["STATUS"])}</td>'
            f'<td style="color:#5a7290">{r["LAST_CHECKED"]}</td>'
            f'</tr>'
        )

    st.markdown(
        _strip_html(f"""
            <div class="dq-table-wrapper">
            <table class="dq-table">
              <thead><tr>
                <th style="text-align:left">DMF Function</th>
                <th style="text-align:center">Type</th>
                <th style="text-align:center">Dimension</th>
                <th style="text-align:center">Colonne</th>
                <th style="text-align:left">DMF Rule</th>
                <th style="text-align:center">Value</th>
                <th style="text-align:center">Status</th>
                <th style="text-align:left">Last Check</th>
              </tr></thead>
              <tbody>{html_rows}</tbody>
            </table>
            </div>
        """),
        unsafe_allow_html=True,
    )

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown("")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="section-title">Status Distribution</div>', unsafe_allow_html=True)
        sc_counts = latest_df["STATUS"].value_counts().reset_index()
        sc_counts.columns = ["Status", "Count"]
        fig_pie = px.pie(
            sc_counts, values="Count", names="Status",
            color="Status",
            color_discrete_map={
                "PASSED": "#2e7d32", "FAILED": "#c62828",
                "NO_DATA": "#757575", "UNKNOWN": "#e65100",
            },
            hole=0.55,
        )
        fig_pie.update_layout(
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            font={"color": CHART_FONT_COLOR}, height=280,
            margin=dict(t=10, b=10, l=0, r=0),
            legend=dict(font=dict(color=CHART_FONT_COLOR)),
        )
        fig_pie.update_traces(
            textinfo="percent+label", textfont_color=CHART_FONT_COLOR,
            marker=dict(line=dict(color="#ffffff", width=2)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_b:
        st.markdown('<div class="section-title">Value by DMF</div>', unsafe_allow_html=True)
        bar_df = latest_df[["DMF_NAME", "ISSUES_FOUND", "STATUS"]].copy()
        bar_df["ISSUES_FOUND"] = pd.to_numeric(bar_df["ISSUES_FOUND"], errors="coerce").fillna(0)
        bar_df = bar_df.sort_values("ISSUES_FOUND", ascending=True)
        fig_bar = go.Figure(go.Bar(
            x=bar_df["ISSUES_FOUND"],
            y=bar_df["DMF_NAME"],
            orientation="h",
            marker_color=[status_to_color(s) for s in bar_df["STATUS"]],
            marker_line_color="#ffffff", marker_line_width=1,
            text=bar_df["ISSUES_FOUND"],
            textposition="outside",
            textfont=dict(color=CHART_FONT_COLOR),
        ))
        fig_bar.update_layout(
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_PLOT_BG,
            font={"color": CHART_FONT_COLOR}, height=280,
            margin=dict(t=10, b=10, l=0, r=30),
            xaxis=dict(showgrid=True, gridcolor=CHART_GRID_COLOR, zeroline=False),
            yaxis=dict(showgrid=False, automargin=True),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    if pd.notna(last_ts):
        st.caption(f"Source: `VW_DQ_LATEST_RESULTS` · Last measurement: {last_ts}")