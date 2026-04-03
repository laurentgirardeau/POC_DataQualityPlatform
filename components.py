# ======================================================================================
# components.py — Reusable UI components and display helpers
#
# All functions here are pure rendering helpers: they take data and return
# HTML strings or call st.* directly. No SQL, no session, no business logic.
# ======================================================================================

import streamlit as st
import pandas as pd

from config import STATUS_COLORS, CHART_FONT_COLOR, CHART_GRID_COLOR, CHART_BG, CHART_PLOT_BG


# ── HTML helper ──────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """
    Strip per-line leading whitespace from an HTML string.

    Streamlit's st.markdown parser treats lines with ≥ 4 leading spaces as
    Markdown preformatted code blocks, causing raw HTML tags like `</div>`
    to appear verbatim instead of being rendered.  Joining stripped lines
    produces compact, whitespace-free HTML that is always rendered correctly.
    """
    return "".join(line.lstrip() for line in html.splitlines())


# ── Color helpers ─────────────────────────────────────────────────────────────

def status_to_color(status: str) -> str:
    """Map a STATUS string to its hex display color."""
    return STATUS_COLORS.get(status, "#757575")


def score_color(score: float) -> str:
    """Return green / orange / red based on quality score thresholds."""
    return "#2e7d32" if score >= 90 else "#e65100" if score >= 70 else "#c62828"


def completeness_color(pct: float | None) -> str:
    """Return green / orange / red based on completeness % thresholds."""
    if pct is None:
        return "#9e9e9e"
    return "#2e7d32" if pct >= 95 else "#e65100" if pct >= 80 else "#c62828"


def score_bar_html(score: float | None) -> str:
    """Render a small inline progress bar for quality score (used in Global View table)."""
    if score is None or pd.isna(score):
        return "—"
    pct   = max(0.0, min(100.0, float(score)))
    color = score_color(pct)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<div class="score-bar-bg" style="flex:1">'
        f'<div class="score-bar-fill" style="width:{pct}%;background:{color}"></div>'
        f'</div>'
        f'<span style="color:{color};font-weight:700;min-width:42px">{pct:.0f}%</span>'
        f'</div>'
    )


def cast_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Cast listed columns to numeric in-place.
    Snowflake / SiS occasionally returns numeric columns as strings.
    """
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Badge renderers ───────────────────────────────────────────────────────────

def render_status_badge(status: str) -> str:
    """Return an HTML badge string for the given STATUS value."""
    return {
        "PASSED":  '<span class="badge-pass">✔ PASSED</span>',
        "FAILED":  '<span class="badge-fail">✖ FAILED</span>',
        "NO_DATA": '<span class="badge-nodata">⏳ NO DATA</span>',
    }.get(status, '<span class="badge-warn">? UNKNOWN</span>')


def render_type_badge(dmf_type: str) -> str:
    """Return an HTML badge string for CORE or CUSTOM DMF type."""
    if dmf_type == "CORE":
        return '<span class="badge-core">⬡ CORE</span>'
    return '<span class="badge-custom">★ CUSTOM</span>'


# ── Streamlit UI components ───────────────────────────────────────────────────

def render_kpi_card(label: str, value: str, color: str = "#1565c0", delta: str = "") -> None:
    """Render a metric card with large value, label, and optional delta."""
    delta_html = f'<div class="kpi-delta" style="color:{color}">{delta}</div>' if delta else ""
    st.markdown(
        _strip_html(f"""
            <div class="kpi-card">
                <div class="kpi-value" style="color:{color}">{value}</div>
                <div class="kpi-label">{label}</div>
                {delta_html}
            </div>
        """),
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str = "") -> None:
    """Render the blue gradient page header banner."""
    subtitle_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        _strip_html(f"""
            <div class="page-header">
                <h2>🛡️ {title}</h2>
                {subtitle_html}
            </div>
        """),
        unsafe_allow_html=True,
    )


def render_health_banner(health: str, minutes_ago: int | None) -> None:
    """
    Render the DMF freshness banner above the tabs.
    health : 'OK' | 'STALE' | 'NO_DATA'
    """
    if health == "OK":
        st.success(f"🟢  DMFs running — last execution **{minutes_ago} min** ago")
    elif health == "STALE":
        st.warning(f"⚠️  No execution for **{minutes_ago} min** — check the DMF schedule")
    else:
        st.error("🔴  No DMF results found. Wait 5–10 min or verify the configuration.")


def render_gauge(value: float, color: str, height: int = 230):
    """Render a Plotly gauge indicator (used in both Global and Detailed views)."""
    import plotly.graph_objects as go

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 44, "color": color}},
        gauge={
            "axis":      {"range": [0, 100], "tickcolor": "#5a7290", "tickfont": {"color": "#5a7290"}},
            "bar":       {"color": color, "thickness": 0.28},
            "bgcolor":   "#f0f5fb",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  70], "color": "#ffebee"},
                {"range": [70, 90], "color": "#fff3e0"},
                {"range": [90,100], "color": "#e8f5e9"},
            ],
            "threshold": {"line": {"color": color, "width": 3}, "thickness": 0.8, "value": value},
        },
        domain={"x": [0.15, 0.85], "y": [0, 1]},
    ))
    fig.update_layout(
        height=height,
        paper_bgcolor=CHART_BG,
        font={"color": CHART_FONT_COLOR, "family": "sans-serif"},
        margin=dict(t=20, b=10, l=0, r=0),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── DQ Platform catalog helpers ───────────────────────────────────────────────

# 6 canonical dimensions — fixed palette
DIMENSIONS_ALL = ["COMPLETENESS", "VALIDITY", "ACCURACY",
                  "CONSISTENCY", "FRESHNESS", "UNIQUENESS"]

_DIM_STYLE: dict[str, tuple[str, str, str]] = {
    # dimension: (bg, fg, border)
    "COMPLETENESS": ("#e8f5e9", "#2e7d32", "#a5d6a7"),
    "VALIDITY":     ("#e3f2fd", "#1565c0", "#90caf9"),
    "ACCURACY":     ("#e0f2f1", "#00695c", "#80cbc4"),
    "CONSISTENCY":  ("#f3e5f5", "#6a1b9a", "#ce93d8"),
    "FRESHNESS":    ("#fff3e0", "#e65100", "#ffcc80"),
    "UNIQUENESS":   ("#ede7f6", "#4527a0", "#b39ddb"),
}

# Static dimension map for CORE (SNOWFLAKE.CORE) DMFs
_CORE_DIMENSION_MAP: dict[str, str] = {
    "NULL_COUNT":         "COMPLETENESS",
    "NULL_PERCENT":       "COMPLETENESS",
    "DUPLICATE_COUNT":    "UNIQUENESS",
    "UNIQUE_COUNT":       "UNIQUENESS",
    "ROW_COUNT":          "CONSISTENCY",
    "PERCENT_ROW_MATCH":  "CONSISTENCY",
    "FRESHNESS":          "FRESHNESS",
    "TIMESTAMP_CHECK":    "FRESHNESS",
    "ACCEPTED_VALUES":    "VALIDITY",
    "REFERENTIAL_CHECK":  "ACCURACY",
}


def build_catalog_lookup(catalog_df) -> dict:
    """
    Build a fast {UPPER(tech_name): {busname, dimension, description, owner}}
    lookup dict from the platform catalog DataFrame.
    """
    if catalog_df is None or catalog_df.empty:
        return {}
    catalog_df = catalog_df.copy()
    catalog_df.columns = [c.upper() for c in catalog_df.columns]
    result = {}
    for _, row in catalog_df.iterrows():
        key = str(row.get("TECH_NAME", "")).upper()
        if key:
            result[key] = {
                "busname":     str(row.get("BUS_NAME", "") or key),
                "dimension":   str(row.get("DIMENSION", "VALIDITY") or "VALIDITY").upper(),
                "description": str(row.get("DESCRIPTION", "") or ""),
                "owner":       str(row.get("OWNER", "") or ""),
            }
    return result


def _infer_dimension_core(dmf_name: str) -> str:
    """Infer DQ dimension from a CORE DMF name using the static map."""
    n = dmf_name.upper()
    for key, dim in _CORE_DIMENSION_MAP.items():
        if key in n:
            return dim
    return "VALIDITY"


def enrich_with_catalog(df, catalog_lookup: dict):
    """
    Add DISPLAY_NAME and DQ_DIMENSION columns to a DMF results DataFrame.

    Rules:
      1. If DMF_NAME is in the platform catalog (tagged CUSTOM) → use busname / dimension
      2. If DMF_NAME is a CORE DMF (DMF_TYPE == 'CORE')         → use static core map
      3. Otherwise                                               → use raw DMF_NAME / VALIDITY
    """
    import pandas as pd

    df = df.copy()

    def _display(row) -> str:
        entry = catalog_lookup.get(str(row.get("DMF_NAME", "")).upper())
        if entry:
            return entry["busname"]
        return str(row.get("DMF_NAME", ""))

    def _dimension(row) -> str:
        entry = catalog_lookup.get(str(row.get("DMF_NAME", "")).upper())
        if entry:
            return entry["dimension"]
        if str(row.get("DMF_TYPE", "")).upper() == "CORE":
            return _infer_dimension_core(str(row.get("DMF_NAME", "")))
        return "VALIDITY"

    df["DISPLAY_NAME"] = df.apply(_display, axis=1)
    df["DQ_DIMENSION"] = df.apply(_dimension, axis=1)
    return df


def compute_dimension_scores(enriched_df) -> dict:
    """
    Compute {dimension: {passed, total, score_pct}} from an enriched DataFrame.
    Only rows with STATUS in PASSED/FAILED are counted (NO_DATA excluded).
    Returns scores for all 6 canonical dimensions; absent ones score as None.

    Deduplication rule (Bug 1 fix):
      When the same DMF is applied to multiple columns of the same table,
      DATA_QUALITY_MONITORING_RESULTS / VW_DQ_LATEST_RESULTS may fan-out to
      several rows. We collapse to one row per (TABLE_NAME, DMF_NAME) keeping
      the worst status (FAILED beats PASSED) before counting.
      For the Detailed View (single table), this is a no-op when one row already
      exists per DMF. When REF_COLUMN_NAME is present (multi-column mode), we
      deduplicate before scoring to count DMF deployments, not column applications.
    """
    import pandas as pd

    result = {}
    if enriched_df is None or enriched_df.empty or "DQ_DIMENSION" not in enriched_df.columns:
        return result

    # Normalise column names to uppercase — Snowpark to_pandas() may return
    # lowercase names in some SiS runtime versions, which would silently break
    # the deduplication check below.
    enriched_df = enriched_df.copy()
    enriched_df.columns = [c.upper() for c in enriched_df.columns]

    active = enriched_df[enriched_df["STATUS"].isin(["PASSED", "FAILED"])].copy()

    # Dedup by (TABLE_NAME, DMF_NAME) — worst-case status wins.
    # "FAILED" < "PASSED" alphabetically → ascending sort puts FAILED first →
    # drop_duplicates(keep="first") keeps the FAILED row when both statuses exist.
    # TABLE_NAME deduplication covers the Global View (schema-level).
    # DMF_NAME-only deduplication covers the Detailed View (single table, no TABLE_NAME col).
    dedup_cols = [c for c in ["TABLE_NAME", "DMF_NAME"] if c in active.columns]
    if dedup_cols:
        active = (
            active.sort_values("STATUS", ascending=True)
            .drop_duplicates(subset=dedup_cols, keep="first")
        )

    for dim in DIMENSIONS_ALL:
        subset = active[active["DQ_DIMENSION"] == dim]
        if subset.empty:
            result[dim] = None
            continue
        passed = int((subset["STATUS"] == "PASSED").sum())
        total  = len(subset)
        result[dim] = {
            "passed": passed,
            "total":  total,
            "score":  round(passed * 100.0 / total, 1) if total > 0 else 0.0,
        }
    return result


def render_dimension_scores(dim_scores: dict, compact: bool = False) -> None:
    """
    Render the 6 dimension score cards.
    compact=True  → smaller cards, used in Summary tab (one row context)
    compact=False → normal cards, used in Global View
    """
    import streamlit as st

    # Build card HTML for each dimension
    cards_html = ""
    for dim in DIMENSIONS_ALL:
        data  = dim_scores.get(dim)
        bg, fg, border = _DIM_STYLE.get(dim, ("#f5f5f5", "#616161", "#bdbdbd"))
        val_size = "1.2rem" if compact else "1.5rem"

        if data is None:
            score_str = "—"
            sub_str   = "No data"
            opacity   = "opacity:.45;"
        else:
            score_str = f"{data['score']:.0f}%"
            sub_str   = f"{data['passed']}/{data['total']}"
            opacity   = ""

        dim_label = dim.capitalize()
        cards_html += (
            f'<div class="dim-score-card" style="background:{bg};border-color:{border};{opacity}">'
            f'<div class="dim-score-val" style="font-size:{val_size};color:{fg}">{score_str}</div>'
            f'<div class="dim-score-name" style="color:{fg}">{dim_label}</div>'
            f'<div class="dim-score-sub" style="color:{fg}">{sub_str}</div>'
            f'</div>'
        )

    st.markdown(
        _strip_html(f'<div class="dim-score-grid">{cards_html}</div>'),
        unsafe_allow_html=True,
    )