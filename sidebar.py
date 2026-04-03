# ======================================================================================
# sidebar.py — Sidebar navigation and Snowflake context selectors
#
# The sidebar drives the entire app: it determines which view is active and
# provides the (db, schema, table) context passed to all render functions.
#
# Cascade logic:
#   DATABASE  → always visible (TTL 3600s)
#   SCHEMA    → always visible, filtered on DATABASE (TTL 3600s)
#   TABLE     → visible only in Detailed View, filtered on DATABASE+SCHEMA (TTL 3600s)
# ======================================================================================

import streamlit as st
from datetime import datetime
from snowflake.snowpark import Session

from config import DEFAULT_DB, DEFAULT_SCHEMA
from queries import get_all_databases, get_all_schemas, get_monitored_tables


def render_sidebar(session: Session) -> dict:
    """
    Render the sidebar and return the navigation context:
    {view, db, schema, table, time_window}
    """
    with st.sidebar:
        st.markdown("## 🛡️ DMF Dashboard")
        st.markdown("*Data Quality Monitoring*")
        st.markdown("---")

        view = st.radio(
            "Navigation",
            ["🏠  Global View", "🔍  Detailed View"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("### 🗄️ Snowflake Context")

        # ── DATABASE ──────────────────────────────────────────────────────────
        try:
            db_list = get_all_databases(session)
        except Exception:
            db_list = []

        db_index = db_list.index(DEFAULT_DB) if DEFAULT_DB in db_list else 0
        db = st.selectbox(
            "Database",
            options=db_list or [DEFAULT_DB],
            index=db_index,
            key="sb_db",
        )

        # ── SCHEMA ────────────────────────────────────────────────────────────
        try:
            schema_list = get_all_schemas(session, db) if db else []
        except Exception:
            schema_list = []

        schema_index = schema_list.index(DEFAULT_SCHEMA) if DEFAULT_SCHEMA in schema_list else 0
        schema = st.selectbox(
            "Schema",
            options=schema_list or [DEFAULT_SCHEMA],
            index=schema_index,
            key="sb_schema",
        )

        # ── TABLE — only visible in Detailed View ─────────────────────────────
        table = ""
        if "Detailed" in view:
            st.markdown("---")
            try:
                tables = get_monitored_tables(session, db, schema) if db and schema else []
            except Exception:
                tables = []

            if tables:
                table = st.selectbox("Table", options=tables, key="sb_table")
            else:
                st.caption("⚠️ No monitored table found in this schema.")

        st.markdown("---")

        # ── Analysis window ───────────────────────────────────────────────────
        time_window = st.select_slider(
            "Analysis window",
            options=[6, 12, 24, 48, 72],
            value=24,
            format_func=lambda x: f"{x}h",
        )

        st.markdown("---")

        # ── Refresh button — clears all cached data ───────────────────────────
        if st.button("🔄  Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown(
            f'<p style="color:#5a7290;font-size:.75rem;margin-top:16px">'
            f'Updated: {datetime.now().strftime("%H:%M:%S")}</p>',
            unsafe_allow_html=True,
        )

    return {
        "view":        view,
        "db":          db,
        "schema":      schema,
        "table":       table,
        "time_window": time_window,
    }
