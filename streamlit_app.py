# ======================================================================================
# streamlit_app.py — Streamlit in Snowflake entry point
#
# This file must be named exactly `streamlit_app.py` for SiS.
# Its only responsibilities:
#   1. Inject global CSS once
#   2. Obtain the active Snowflake session
#   3. Render the sidebar and route to the correct view
#   4. Catch and display unhandled errors
#
# All business logic lives in the imported modules:
#   config.py           constants + CSS_STYLES
#   queries.py          SQL functions (@st.cache_data)
#   components.py       UI building blocks
#   sidebar.py          render_sidebar()
#   view_global.py      render_global_view()
#   view_detailed.py    render_detailed_view()
#     ├── view_tab_summary.py
#     ├── view_tab_detail.py
#     └── view_tab_history.py
# ======================================================================================

import streamlit as st
from snowflake.snowpark.context import get_active_session

from config import CSS_STYLES
from sidebar import render_sidebar
from view_global import render_global_view
from view_detailed import render_detailed_view

# ── Inject CSS once — must be at module level for SiS ────────────────────────
st.markdown(CSS_STYLES, unsafe_allow_html=True)


def main() -> None:
    try:
        session = get_active_session()
        params  = render_sidebar(session)

        db     = params["db"]
        schema = params["schema"]
        table  = params["table"]
        view   = params["view"]
        time_w = params["time_window"]

        if not db or not schema:
            st.info("👈  Select a Database and Schema in the sidebar.")
            return

        if "Global" in view:
            render_global_view(session, db, schema)
        else:
            render_detailed_view(session, db, schema, table, time_w)

    except Exception as e:
        st.error(f"❌ Connection or execution error: {e}")
        st.info(
            "Please verify that:\n"
            "- The app role has `DATABASE ROLE SNOWFLAKE.DATA_METRIC_USER`\n"
            "- At least one DMF has been executed on a table in the selected schema\n"
            "- The Database and Schema are correctly selected"
        )
        with st.expander("🔧 Error details"):
            st.exception(e)


# SiS: __name__ is never '__main__' — call main() directly
main()
