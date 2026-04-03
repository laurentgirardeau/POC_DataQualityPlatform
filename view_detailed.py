# ======================================================================================
# view_detailed.py — Detailed View coordinator (table-level)
#
# Responsibilities:
#   1. Validate that a table is selected
#   2. Load latest DMF results (the only query needed before the tabs)
#   3. Derive KPIs and health status in Python — no extra SQL
#   4. Render page header and health banner (common to all tabs)
#   5. Create the 3 tabs and dispatch to dedicated render functions
#
# Each tab is lazy: its SQL queries run only when the tab is active.
# ======================================================================================

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from snowflake.snowpark import Session

from queries import get_table_dmf_results, get_custom_dmf_catalog
from components import (
    render_page_header,
    render_health_banner,
    score_color,
    build_catalog_lookup,
    enrich_with_catalog,
    compute_dimension_scores,
)
from view_tab_summary import render_tab_summary
from view_tab_detail  import render_tab_table_detail
from view_tab_history import render_tab_history


def render_detailed_view(
    session: Session,
    db: str,
    schema: str,
    table: str,
    time_window: int,
) -> None:
    """
    Detailed View — table-level drill-down, 3 tabs.

    Pre-tab data load (1 query):
      get_table_dmf_results() → latest_df_pre
        ├── KPIs derived in Python (total, passed, failed, score)
        ├── Health banner derived from LAST_CHECKED max
        └── Passed to tab_summary and tab_detail (0 extra queries)

    Tabs (all lazy):
      📊 Summary     → view_tab_summary.render_tab_summary()
      🔍 Table Detail → view_tab_detail.render_tab_table_detail()
      📋 History     → view_tab_history.render_tab_history()
    """
    if not table:
        st.info("👈  Select a table in the sidebar to get started.")
        return

    # ── Page header ───────────────────────────────────────────────────────────
    render_page_header(
        title="Detailed View — DMF Results",
        subtitle=f"Table: {db}.{schema}.{table}",
    )

    # ── Load DMF catalog (tagged CUSTOM functions) ───────────────────────────
    catalog_df     = get_custom_dmf_catalog(session, db)
    catalog_lookup = build_catalog_lookup(catalog_df)

    # ── Single pre-tab query: VW_DQ_LATEST_RESULTS ────────────────────────────
    latest_df_pre = get_table_dmf_results(session, db, schema, table)

    if latest_df_pre.empty:
        st.warning("No DMF results found for this table.")
        return

    latest_df_pre["ISSUES_FOUND"] = pd.to_numeric(latest_df_pre["ISSUES_FOUND"], errors="coerce")

    # Enrich with DISPLAY_NAME (busname) and DQ_DIMENSION from catalog
    latest_df_pre = enrich_with_catalog(latest_df_pre, catalog_lookup)

    # ── KPI derivation (Python only) ──────────────────────────────────────────
    total   = len(latest_df_pre)
    passed  = int((latest_df_pre["STATUS"] == "PASSED").sum())
    failed  = int((latest_df_pre["STATUS"] == "FAILED").sum())
    score   = round(passed * 100.0 / total, 1) if total > 0 else 0.0
    last_ts = pd.to_datetime(latest_df_pre["LAST_CHECKED"], errors="coerce").max()
    sc        = score_color(score)
    dim_scores = compute_dimension_scores(latest_df_pre)   # passed to all tabs

    # ── Health banner (Python only, no SQL) ───────────────────────────────────
    if pd.notna(last_ts):
        now_utc     = datetime.now(timezone.utc)
        last_utc    = last_ts.tz_localize("UTC") if last_ts.tzinfo is None else last_ts
        minutes_ago = int((now_utc - last_utc).total_seconds() / 60)
        render_health_banner(
            health="OK" if minutes_ago < 30 else "STALE",
            minutes_ago=minutes_ago,
        )
    else:
        render_health_banner(health="NO_DATA", minutes_ago=None)

    # ── 3 Tabs ────────────────────────────────────────────────────────────────
    tab_summary, tab_detail, tab_history = st.tabs([
        "📊  Summary",
        "🔍  Table Detail",
        "📋  History",
    ])

    with tab_summary:
        render_tab_summary(
            score=score,
            sc=sc,
            total=total,
            passed=passed,
            failed=failed,
            last_ts=last_ts,
            latest_df=latest_df_pre,
            dim_scores=dim_scores,
        )

    with tab_detail:
        # latest_df_pre reused — 0 extra SQL
        render_tab_table_detail(session, db, schema, table, latest_df_pre)

    with tab_history:
        render_tab_history(session, db, schema, table, time_window, last_ts,
                           dim_scores=dim_scores)