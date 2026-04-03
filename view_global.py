# ======================================================================================
# view_global.py — Global View (schema-level)
#
# Renders a consolidated quality overview for all monitored tables in the
# selected schema. One SQL query (get_schema_table_scores) — all KPIs and
# charts are derived in Python from the same DataFrame.
# ======================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from snowflake.snowpark import Session

from config import CHART_FONT_COLOR, CHART_GRID_COLOR, CHART_BG, CHART_PLOT_BG
from queries import (
    get_schema_table_scores,
    get_schema_latest_dmf_results,
    get_custom_dmf_catalog,
)
from components import (
    _strip_html,
    cast_numeric,
    render_kpi_card,
    render_page_header,
    render_gauge,
    score_color,
    score_bar_html,
    build_catalog_lookup,
    enrich_with_catalog,
    compute_dimension_scores,
    render_dimension_scores,
)


def render_global_view(session: Session, db: str, schema: str) -> None:
    """
    Schema-level quality summary:
      - 5 KPI cards (schema aggregation derived in Python)
      - Quality gauge
      - Per-table score table
      - Status distribution pie + score bar chart
    """
    render_page_header(
        title="Global View — Data Quality",
        subtitle=f"Schema: {db}.{schema}",
    )

    # ── Single data load — KPIs derived in Python (no extra SQL) ─────────────
    scores_df = get_schema_table_scores(session, db, schema)
    scores_df  = cast_numeric(scores_df, [
        "TOTAL_DMFS", "CORE_DMFS", "CUSTOM_DMFS",
        "PASSED_CHECKS", "FAILED_CHECKS", "QUALITY_SCORE_PCT",
    ])

    if scores_df.empty:
        st.warning(
            "No monitored tables found in this schema. "
            "Verify that DMFs have been executed at least once."
        )
        return

    # Load catalog + schema-level DMF results for dimension scores
    catalog_lookup = build_catalog_lookup(get_custom_dmf_catalog(session, db))
    schema_dmf_df  = get_schema_latest_dmf_results(session, db, schema)
    if not schema_dmf_df.empty:
        schema_dmf_df = enrich_with_catalog(schema_dmf_df, catalog_lookup)

    total_tables = len(scores_df)
    total_passed = int(scores_df["PASSED_CHECKS"].sum() or 0)
    total_failed = int(scores_df["FAILED_CHECKS"].sum() or 0)
    total_checks = total_passed + total_failed
    score        = round(total_passed * 100.0 / total_checks, 1) if total_checks > 0 else 0.0
    last_ts      = pd.to_datetime(scores_df["LAST_CHECK_TIME"], errors="coerce").max()
    sc           = score_color(score)

    # ── 5 KPI cards ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: render_kpi_card("Quality Score",    f"{score:.1f}%",   color=sc)
    with c2: render_kpi_card("Monitored Tables", str(total_tables), color="#1565c0")
    with c3: render_kpi_card("Total Checks",     str(total_checks), color="#1565c0")
    with c4: render_kpi_card("Passed",           str(total_passed), color="#2e7d32")
    with c5: render_kpi_card("Failed",           str(total_failed), color="#c62828")

    # ── Dimension scores — inline under KPI cards ─────────────────────────────
    dim_scores = compute_dimension_scores(schema_dmf_df) if not schema_dmf_df.empty else {}
    render_dimension_scores(dim_scores)

    st.markdown("")

    # ── Quality gauge ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Overall Quality Score — Schema</div>', unsafe_allow_html=True)
    render_gauge(score, sc)

    # ── Per-table score table ─────────────────────────────────────────────────
    st.markdown('<div class="section-title">Table-Level Quality Scores</div>', unsafe_allow_html=True)

    scores_df["LAST_CHECK_TIME"] = (
        pd.to_datetime(scores_df["LAST_CHECK_TIME"], errors="coerce")
        .dt.strftime("%Y-%m-%d %H:%M")
        .fillna("—")
    )

    html_rows = ""
    for _, r in scores_df.iterrows():
        tbl_score   = float(r["QUALITY_SCORE_PCT"]) if pd.notna(r["QUALITY_SCORE_PCT"]) else None
        passed      = int(r["PASSED_CHECKS"] or 0)
        failed      = int(r["FAILED_CHECKS"] or 0)
        total_dmfs  = int(r["TOTAL_DMFS"]    or 0)
        core_dmfs   = int(r["CORE_DMFS"]     or 0)
        custom_dmfs = int(r["CUSTOM_DMFS"]   or 0)
        fail_color  = "#c62828" if failed > 0 else "#2e7d32"
        html_rows += (
            f'<tr>'
            f'<td style="font-weight:600">{r["TABLE_NAME"]}</td>'
            f'<td style="min-width:140px">{score_bar_html(tbl_score)}</td>'
            f'<td style="text-align:center">{total_dmfs}</td>'
            f'<td style="text-align:center"><span class="badge-core">⬡ {core_dmfs}</span></td>'
            f'<td style="text-align:center"><span class="badge-custom">★ {custom_dmfs}</span></td>'
            f'<td style="text-align:center;color:#2e7d32;font-weight:700">{passed}</td>'
            f'<td style="text-align:center;color:{fail_color};font-weight:700">{failed}</td>'
            f'<td style="color:#5a7290">{r["LAST_CHECK_TIME"]}</td>'
            f'</tr>'
        )

    st.markdown(
        _strip_html(f"""
            <div class="dq-table-wrapper">
            <table class="dq-table">
              <thead><tr>
                <th style="text-align:left">Table</th>
                <th style="text-align:left">Quality Score</th>
                <th style="text-align:center">DMFs</th>
                <th style="text-align:center">Core</th>
                <th style="text-align:center">Custom</th>
                <th style="text-align:center">Passed</th>
                <th style="text-align:center">Failed</th>
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
        st.markdown('<div class="section-title">Check Status Distribution</div>', unsafe_allow_html=True)
        pie_data = pd.DataFrame({
            "Status": ["PASSED", "FAILED"],
            "Count":  [total_passed, total_failed],
        })
        fig_pie = px.pie(
            pie_data, values="Count", names="Status",
            color="Status",
            color_discrete_map={"PASSED": "#2e7d32", "FAILED": "#c62828"},
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
        st.markdown('<div class="section-title">Quality Score by Table</div>', unsafe_allow_html=True)
        bar_df = scores_df[["TABLE_NAME", "QUALITY_SCORE_PCT"]].copy()
        bar_df["QUALITY_SCORE_PCT"] = pd.to_numeric(bar_df["QUALITY_SCORE_PCT"], errors="coerce").fillna(0)
        bar_df = bar_df.sort_values("QUALITY_SCORE_PCT", ascending=True)
        fig_bar = go.Figure(go.Bar(
            x=bar_df["QUALITY_SCORE_PCT"],
            y=bar_df["TABLE_NAME"],
            orientation="h",
            marker_color=[score_color(v) for v in bar_df["QUALITY_SCORE_PCT"]],
            marker_line_color="#ffffff", marker_line_width=1,
            text=bar_df["QUALITY_SCORE_PCT"].apply(lambda v: f"{v:.0f}%"),
            textposition="outside",
            textfont=dict(color=CHART_FONT_COLOR),
        ))
        fig_bar.update_layout(
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_PLOT_BG,
            font={"color": CHART_FONT_COLOR},
            height=max(200, len(bar_df) * 40 + 60),
            margin=dict(t=10, b=10, l=0, r=50),
            xaxis=dict(showgrid=True, gridcolor=CHART_GRID_COLOR, zeroline=False, range=[0, 115]),
            yaxis=dict(showgrid=False, automargin=True),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    if pd.notna(last_ts):
        st.caption(f"Source: `VW_DQ_TABLE_SCORES` · Last measurement: {last_ts}")