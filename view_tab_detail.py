# ======================================================================================
# view_tab_detail.py — Onglet 🔍 Table Detail (Detailed View)
#
# Layout:
#   Left  (≈2/3) : Table tabulaire scrollable — nom, type, description, badges
#                  contraintes (PK/NN/U), barre de complétude.
#                  Métriques globales + barre de recherche au-dessus.
#   Right (≈1/3) : Panneau détail du champ sélectionné :
#                    1. En-tête & métadonnées
#                    2. Data Profiling
#                    3. Règles DQ actives (carte par DMF)
#
# Requêtes (toutes avec cache) :
#   get_table_column_metadata()    TTL 3600s — liste colonnes + contraintes + description
#   get_all_columns_completeness() TTL 300s  — scan unique, toutes colonnes
#   get_column_profile()           TTL 300s  — lazy, au clic colonne
#   get_column_profiling_extended()TTL 300s  — lazy, au clic colonne
#   get_column_top_values()        TTL 300s  — lazy, détection de pattern
#   latest_df                      0 requête — DMF rules du chargement pré-onglet
# ======================================================================================

import re
import streamlit as st
import pandas as pd

from config import CHART_FONT_COLOR, CHART_BG, CHART_PLOT_BG, CHART_GRID_COLOR
from components import (
    _strip_html,
    cast_numeric,
    render_status_badge,
    status_to_color,
    completeness_color,
)
from queries import (
    get_table_column_metadata,
    get_column_pk_unique_constraints,
    get_all_columns_completeness,
    get_column_profile,
    get_column_profiling_extended,
    get_column_top_values,
    get_table_dmf_column_refs,
)


# ── Type classification ───────────────────────────────────────────────────────

_NUMERIC = frozenset({
    "NUMBER","INT","INTEGER","BIGINT","SMALLINT","TINYINT","BYTEINT",
    "FLOAT","FLOAT4","FLOAT8","DOUBLE","REAL","DECIMAL","NUMERIC",
})
_DATE = frozenset({
    "DATE","DATETIME","TIME",
    "TIMESTAMP","TIMESTAMP_LTZ","TIMESTAMP_NTZ","TIMESTAMP_TZ",
})
_BOOL = frozenset({"BOOLEAN"})
_TEXT = frozenset({
    "TEXT","VARCHAR","CHAR","CHARACTER","STRING",
    "NCHAR","NVARCHAR","NVARCHAR2","CHAR VARYING","NCHAR VARYING",
})

def _base(dt: str) -> str:
    return dt.upper().split("(")[0].strip()

def dtype_css(dt: str) -> tuple[str, str]:
    b = _base(dt)
    if b in _NUMERIC: return "dt-number", "NUM"
    if b in _DATE:    return "dt-date",   "DATE"
    if b in _BOOL:    return "dt-bool",   "BOOL"
    if b in _TEXT:    return "dt-text",   "TEXT"
    return "dt-other", b[:6]

def is_numeric(dt: str) -> bool: return _base(dt) in _NUMERIC
def is_text(dt: str) -> bool:    return _base(dt) in _TEXT


# ── DMF dimension mapping ─────────────────────────────────────────────────────

_DIM_MAP = {
    "NULL_COUNT":"Completeness","NULL_PERCENT":"Completeness",
    "ROW_COUNT":"Volume","DUPLICATE_COUNT":"Uniqueness","UNIQUE_COUNT":"Uniqueness",
    "FRESHNESS":"Freshness","PERCENT_ROW_MATCH":"Consistency",
    "REFERENTIAL":"Consistency","ACCEPTED_VALUES":"Validity",
}
_DIM_COLORS = {
    "Completeness":("#e8f5e9","#2e7d32"),"Uniqueness":("#e3f2fd","#1565c0"),
    "Volume":("#fff3e0","#e65100"),"Freshness":("#f3e5f5","#6a1b9a"),
    "Consistency":("#fce4ec","#c62828"),"Validity":("#f5f5f5","#616161"),
}

def _dimension(name: str) -> str:
    n = name.upper()
    for k, v in _DIM_MAP.items():
        if k in n:
            return v
    return "Validity"


# ── Pattern detection ─────────────────────────────────────────────────────────

_PAT = [
    ("Email",          r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"),
    ("Téléphone",      r"^\+?[\d\s\-\(\)\.]{7,20}$"),
    ("Date ISO",       r"^\d{4}-\d{2}-\d{2}$"),
    ("Date FR",        r"^\d{2}/\d{2}/\d{4}$"),
    ("DateTime ISO",   r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
    ("UUID",           r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
    ("Entier (str)",   r"^\d+$"),
    ("Décimal (str)",  r"^\d+[.,]\d+$"),
    ("Code MAJ",       r"^[A-Z0-9_\-]{2,20}$"),
    ("Flag bool",      r"^(true|false|yes|no|0|1|Y|N)$"),
]

def detect_pattern(values: list) -> str:
    clean = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not clean:
        return "—"
    for name, regex in _PAT:
        if all(re.match(regex, v, re.IGNORECASE) for v in clean):
            return name
    lengths = {len(v) for v in clean}
    if len(lengths) == 1:
        return f"Longueur fixe ({lengths.pop()} car.)"
    return "Texte libre / Mixte"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dot_class(col: str, latest_df: pd.DataFrame, column_refs_map: dict | None = None) -> str:
    """Compute dot colour class for a column based on its linked DMF statuses."""
    if latest_df.empty:
        return "nodata"
    # Normalise: Snowpark may return lowercase column names in some SiS versions
    df = latest_df.copy()
    df.columns = [c.upper() for c in df.columns]
    cu = col.strip().upper()
    if column_refs_map and cu in column_refs_map:
        dmf_names = {n.upper() for n in column_refs_map[cu]}
        m = df[df["DMF_NAME"].str.upper().isin(dmf_names)]
    elif column_refs_map:
        # column_refs_map available but no entry for this column → no DMF
        return "nodata"
    else:
        # No refs map: match by DMF_NAME or DMF_RULE containment (last resort)
        mn = df["DMF_NAME"].str.upper().str.contains(cu, na=False, regex=False)
        mr = df.get("DMF_RULE", pd.Series(dtype=str)).str.upper().str.contains(cu, na=False, regex=False)
        m  = df[mn | mr]
    if m.empty:
        return "nodata"
    return "fail" if (m["STATUS"] == "FAILED").any() else "pass"

def _fmt(raw, spec: str = "") -> str:
    if raw is None:
        return "—"
    try:
        if pd.isna(raw):
            return "—"
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if s in ("", "None", "nan", "NaN", "NaT"):
        return "—"
    if spec:
        try:
            return spec.format(float(raw))
        except Exception:
            pass
    return s

def _constraint_badges(nullable: str, ctypes: str) -> str:
    ct = (ctypes or "").upper()
    b  = ""
    if "PRIMARY KEY" in ct:
        b += '<span class="badge-pk">PK</span> '
    if "UNIQUE" in ct and "PRIMARY KEY" not in ct:
        b += '<span class="badge-uq">U</span> '
    if nullable in ("NO", "N"):
        b += '<span class="badge-nn">NN</span>'
    return b.strip()

_DOT_COLORS = {"pass":"#2e7d32","fail":"#c62828","nodata":"#9e9e9e"}


# ════════════════════════════════════════════════════════════════════════════
# SECTION RENDERERS (right panel)
# ════════════════════════════════════════════════════════════════════════════

def _section_metadata(meta: pd.Series, completeness_map: dict) -> None:
    col_name    = meta["COLUMN_NAME"]
    data_type   = meta["DATA_TYPE"]
    description = str(meta.get("DESCRIPTION", "") or "").strip()
    ctypes      = str(meta.get("CONSTRAINT_TYPES", "") or "")
    nullable    = meta.get("IS_NULLABLE", "YES")
    char_max    = meta.get("CHARACTER_MAXIMUM_LENGTH")
    num_prec    = meta.get("NUMERIC_PRECISION")
    num_scale   = meta.get("NUMERIC_SCALE")

    # Full type string
    type_full = data_type
    if char_max and not pd.isna(char_max):
        type_full += f"({int(char_max)})"
    elif num_prec and not pd.isna(num_prec):
        sc = f",{int(num_scale)}" if num_scale and not pd.isna(num_scale) else ""
        type_full += f"({int(num_prec)}{sc})"

    # Constraints label
    ct = ctypes.upper()
    cl = []
    if "PRIMARY KEY" in ct: cl.append("Clé primaire")
    if "UNIQUE" in ct and "PRIMARY KEY" not in ct: cl.append("Unique")
    if nullable in ("NO", "N"): cl.append("Not Null")
    c_str = " · ".join(cl) or "Aucune"

    comp = completeness_map.get(col_name)
    comp_str = f"{comp:.1f}%" if comp is not None else "—"

    st.markdown(_strip_html(f"""
        <div class="meta-grid">
            <div class="meta-card">
                <div class="meta-card-label">Nom technique</div>
                <div class="meta-card-value" style="font-family:Consolas,monospace">{col_name}</div>
            </div>
            <div class="meta-card">
                <div class="meta-card-label">Type complet</div>
                <div class="meta-card-value">{type_full}</div>
            </div>
            <div class="meta-card">
                <div class="meta-card-label">Contraintes</div>
                <div class="meta-card-value">{c_str}</div>
            </div>
            <div class="meta-card">
                <div class="meta-card-label">Complétude</div>
                <div class="meta-card-value">{comp_str}</div>
            </div>
        </div>
    """), unsafe_allow_html=True)

    if description:
        st.markdown(_strip_html(f"""
            <div class="meta-card" style="margin-bottom:12px">
                <div class="meta-card-label">Description métier</div>
                <div class="meta-card-value" style="font-style:italic;color:#3a5a7a">{description}</div>
            </div>
        """), unsafe_allow_html=True)


def _section_profiling(session, db, schema, table, col_name, data_type, completeness_map) -> None:
    num  = is_numeric(data_type)
    txt  = is_text(data_type)

    st.markdown('<div class="section-title">Data Profiling</div>', unsafe_allow_html=True)

    # Core profile
    try:
        pf = get_column_profile(session, db, schema, table, col_name, num)
        cast_numeric(pf, ["TOTAL_ROWS","NON_NULL_COUNT","DISTINCT_COUNT"])
        p  = pf.iloc[0]
        total    = int(p["TOTAL_ROWS"]    or 0)
        non_null = int(p["NON_NULL_COUNT"] or 0)
        distinct = int(p["DISTINCT_COUNT"] or 0)
        comp_pct = completeness_map.get(col_name)
        if comp_pct is None:
            comp_pct = round(non_null * 100.0 / total, 1) if total > 0 else 0.0
        comp_c = completeness_color(comp_pct)

        # Completeness bar
        st.markdown(_strip_html(f"""
            <div style="margin-bottom:14px">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
                    <span style="font-size:.75rem;font-weight:700;color:#5a7290;text-transform:uppercase;letter-spacing:.05em">Complétude</span>
                    <span style="font-weight:700;font-size:1.05rem;color:{comp_c}">{comp_pct:.1f}%</span>
                </div>
                <div style="background:#e0e0e0;border-radius:5px;height:8px">
                    <div style="width:{comp_pct:.0f}%;height:8px;border-radius:5px;background:{comp_c}"></div>
                </div>
                <div style="font-size:.73rem;color:#5a7290;margin-top:3px">
                    {non_null:,} valeurs renseignées / {total:,} lignes
                </div>
            </div>
        """), unsafe_allow_html=True)

        # Cardinality row
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(_strip_html(f"""
                <div class="stat-card">
                    <div class="stat-val">{distinct:,}</div>
                    <div class="stat-label">Valeurs uniques</div>
                </div>
            """), unsafe_allow_html=True)
        with c2:
            null_count = total - non_null
            st.markdown(_strip_html(f"""
                <div class="stat-card">
                    <div class="stat-val">{null_count:,}</div>
                    <div class="stat-label">Valeurs nulles</div>
                </div>
            """), unsafe_allow_html=True)
    except Exception:
        total = 0
        st.caption("Profil de base indisponible — vérifiez le privilège SELECT.")

    # Extended profile
    try:
        ext_df = get_column_profiling_extended(session, db, schema, table, col_name, num, txt)
        cast_numeric(ext_df, ["MIN_LENGTH","MAX_LENGTH","AVG_LENGTH",
                               "MEAN_VAL","STD_VAL","OUTLIER_COUNT"])
        ext = ext_df.iloc[0]

        st.markdown("")
        if txt:
            c1, c2, c3 = st.columns(3)
            for widget, val, lbl in [
                (c1, _fmt(ext["MIN_LENGTH"],"{:.0f}"), "Long. min"),
                (c2, _fmt(ext["MAX_LENGTH"],"{:.0f}"), "Long. max"),
                (c3, _fmt(ext["AVG_LENGTH"],"{:.1f}"), "Long. moy."),
            ]:
                with widget:
                    st.markdown(_strip_html(f"""
                        <div class="stat-card">
                            <div class="stat-val">{val}</div>
                            <div class="stat-label">{lbl}</div>
                        </div>
                    """), unsafe_allow_html=True)

        elif num:
            outliers = int(ext["OUTLIER_COUNT"] or 0) if pd.notna(ext.get("OUTLIER_COUNT")) else 0
            tot = total if total > 0 else 1
            ratio = round(outliers * 100.0 / tot, 1)
            oc = "#c62828" if ratio > 5 else "#e65100" if ratio > 1 else "#2e7d32"

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(_strip_html(f"""
                    <div class="stat-card">
                        <div class="stat-val">{_fmt(ext["MEAN_VAL"],"{:.2f}")}</div>
                        <div class="stat-label">Moyenne</div>
                    </div>
                """), unsafe_allow_html=True)
            with c2:
                st.markdown(_strip_html(f"""
                    <div class="stat-card">
                        <div class="stat-val">{_fmt(ext["STD_VAL"],"{:.2f}")}</div>
                        <div class="stat-label">Écart-type</div>
                    </div>
                """), unsafe_allow_html=True)

            st.markdown("")
            c3, c4 = st.columns(2)
            with c3:
                st.markdown(_strip_html(f"""
                    <div class="stat-card">
                        <div class="stat-val" style="color:{oc}">{outliers:,}</div>
                        <div class="stat-label">Valeurs atypiques (3σ)</div>
                    </div>
                """), unsafe_allow_html=True)
            with c4:
                st.markdown(_strip_html(f"""
                    <div class="stat-card">
                        <div class="stat-val" style="color:{oc}">{ratio:.1f}%</div>
                        <div class="stat-label">Ratio atypiques</div>
                    </div>
                """), unsafe_allow_html=True)
    except Exception:
        pass

    # Pattern (text only)
    if txt:
        try:
            tv = get_column_top_values(session, db, schema, table, col_name, limit=20)
            tv.columns = [c.upper() for c in tv.columns]
            pattern = detect_pattern(tv["VALUE"].tolist()) if not tv.empty else "—"
            st.markdown("")
            st.markdown(_strip_html(f"""
                <div class="meta-card">
                    <div class="meta-card-label">Pattern détecté</div>
                    <div class="meta-card-value">{pattern}</div>
                </div>
            """), unsafe_allow_html=True)
        except Exception:
            pass


def _section_dq_rules(
    col_name: str,
    latest_df: pd.DataFrame,
    column_refs_map: dict | None = None,
) -> None:
    """
    Display DQ rule cards for the selected column.

    column_refs_map: {COLUMN_NAME_UPPER: [DMF_NAME_UPPER, ...]} from
                     DATA_METRIC_FUNCTION_REFERENCES.

    Matching strategy (in order of reliability):
      1. column_refs_map populated  → exact match by DMF name (most accurate)
      2. column_refs_map empty      → show all table-level DMFs (graceful fallback
                                       when DATA_METRIC_FUNCTION_REFERENCES is not
                                       accessible; user sees all rules, not none)

    The section is hidden ONLY when column_refs_map is available AND confirms
    that no DMF is linked to this column.
    """
    if latest_df.empty:
        return  # No DMF results for the table — section hidden entirely

    # Normalise DMF names to uppercase for reliable matching
    df = latest_df.copy()
    df.columns = [c.upper() for c in df.columns]
    cu = col_name.strip().upper()

    if column_refs_map:
        # Reliable path: DATA_METRIC_FUNCTION_REFERENCES is available
        dmf_names_for_col = {n.upper() for n in column_refs_map.get(cu, [])}
        if not dmf_names_for_col:
            return  # Column confirmed to have no linked DMFs → hide section
        linked = df[df["DMF_NAME"].str.upper().isin(dmf_names_for_col)]
        if linked.empty:
            return
    else:
        # Fallback: column refs unavailable → show all table-level DMFs
        # Better to show too much than nothing when we can't determine the mapping
        linked = df

    st.markdown('<div class="section-title">Règles DQ actives</div>', unsafe_allow_html=True)

    for _, dmf in linked.iterrows():
        dim              = _dimension(dmf["DMF_NAME"])
        dim_bg, dim_fg   = _DIM_COLORS.get(dim, ("#f5f5f5","#616161"))
        status           = dmf.get("STATUS", "NO_DATA")
        s_color          = status_to_color(status)

        issues = dmf.get("ISSUES_FOUND")
        try:
            issues_str = f"{int(pd.to_numeric(issues, errors='coerce') or 0):,}"
        except Exception:
            issues_str = "—"

        last_chk = dmf.get("LAST_CHECKED", "")
        try:
            last_chk = pd.to_datetime(last_chk, errors="coerce").strftime("%Y-%m-%d %H:%M")
        except Exception:
            last_chk = str(last_chk) if last_chk else "—"

        dmf_rule = str(dmf.get("DMF_RULE", "—")) or "—"

        st.markdown(_strip_html(f"""
            <div class="dq-rule-card">
                <div class="dq-rule-card-header">
                    <span class="dq-rule-name">{dmf['DMF_NAME']}</span>
                    <span class="dq-dimension" style="background:{dim_bg};color:{dim_fg}">{dim}</span>
                </div>
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
                    {render_status_badge(status)}
                    <span style="font-size:.82rem;color:{s_color};font-weight:700">{issues_str} anomalie(s)</span>
                </div>
                <div class="dq-rule-meta">
                    Règle : <code style="background:#f0f5fb;padding:1px 5px;border-radius:4px">{dmf_rule}</code>
                </div>
                <div class="dq-rule-meta" style="margin-top:4px">Dernier contrôle : {last_chk}</div>
            </div>
        """), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ════════════════════════════════════════════════════════════════════════════

def render_tab_table_detail(
    session, db: str, schema: str, table: str, latest_df: pd.DataFrame,
) -> None:
    """
    Table Detail tab.
    Left 2/3  : column table with search + global metrics strip.
    Right 1/3 : selected column detail.
    """
    # Load column metadata (COLUMNS view only — no elevated privileges needed)
    meta_df = get_table_column_metadata(session, db, schema, table)
    if meta_df.empty:
        st.info("Métadonnées indisponibles — vérifiez le privilège SELECT.")
        return
    meta_df.columns = [c.upper() for c in meta_df.columns]

    # Enrich with PK/UNIQUE constraints — silently falls back to {} if not authorized
    # (KEY_COLUMN_USAGE requires MANAGE GRANTS which may not be available in SiS)
    pk_uq_map = get_column_pk_unique_constraints(session, db, schema, table)
    if pk_uq_map:
        meta_df["CONSTRAINT_TYPES"] = meta_df["COLUMN_NAME"].map(pk_uq_map).fillna("")

    # Bulk completeness — single table scan
    col_tuple        = tuple(meta_df["COLUMN_NAME"].tolist())
    completeness_map = get_all_columns_completeness(session, db, schema, table, col_tuple)

    # Column → DMF mapping from DATA_METRIC_FUNCTION_REFERENCES.
    # column_refs_map: {COLUMN_NAME_UPPER: [DMF_NAME_UPPER, ...]}
    # When DATA_METRIC_FUNCTION_REFERENCES is inaccessible, refs_df is empty
    # and column_refs_map stays {}.  _section_dq_rules handles this gracefully.
    refs_df = get_table_dmf_column_refs(session, db, schema, table)
    column_refs_map: dict = {}
    if not refs_df.empty:
        refs_df.columns = [c.upper() for c in refs_df.columns]   # guard against lowercase
        for _, ref_row in refs_df.iterrows():
            col_key = str(ref_row.get("REF_COLUMN_NAME", "") or "").strip().upper()
            dmf_nm  = str(ref_row.get("DMF_NAME", "") or "").strip().upper()
            if col_key and dmf_nm:
                column_refs_map.setdefault(col_key, []).append(dmf_nm)

    # Session state for selected column (resets on table change via key)
    ss_key = f"td_{db}_{schema}_{table}"
    if ss_key not in st.session_state:
        st.session_state[ss_key] = None

    # ── Global metrics strip ──────────────────────────────────────────────
    n_total   = len(meta_df)
    n_constr  = int(
        (
            meta_df["IS_NULLABLE"].isin(["NO","N"]) |
            (meta_df["CONSTRAINT_TYPES"].fillna("").str.len() > 0)
        ).sum()
    )
    avg_comp  = round(sum(completeness_map.values()) / len(completeness_map), 1) if completeness_map else 0.0
    avg_c     = completeness_color(avg_comp)
    cap_note  = f'<div class="td-metric-sep"></div><div style="font-size:.75rem;color:#e65100;align-self:center">⚠ {min(len(col_tuple),200)} col. max</div>' if len(col_tuple) > 200 else ""

    st.markdown(_strip_html(f"""
        <div class="td-metrics-strip">
            <div>
                <div class="td-metric-val">{n_total}</div>
                <div class="td-metric-lbl">Colonnes</div>
            </div>
            <div class="td-metric-sep"></div>
            <div>
                <div class="td-metric-val">{n_constr}</div>
                <div class="td-metric-lbl">Avec contraintes</div>
            </div>
            <div class="td-metric-sep"></div>
            <div>
                <div class="td-metric-val" style="color:{avg_c}">{avg_comp:.1f}%</div>
                <div class="td-metric-lbl">Complétude moy.</div>
            </div>
            {cap_note}
        </div>
    """), unsafe_allow_html=True)

    # ── Search ────────────────────────────────────────────────────────────
    search = st.text_input("", key="td_search", placeholder="🔍  Rechercher une colonne…",
                           label_visibility="collapsed")

    # Filter
    filtered = meta_df.copy()
    if search.strip():
        q = search.strip().lower()
        m = (
            filtered["COLUMN_NAME"].str.lower().str.contains(q, na=False) |
            filtered["DATA_TYPE"].str.lower().str.contains(q, na=False)   |
            filtered["DESCRIPTION"].fillna("").str.lower().str.contains(q, na=False)
        )
        filtered = filtered[m]

    # ── Two-panel layout ──────────────────────────────────────────────────
    left, right = st.columns([2, 1])

    # ══════════════════ LEFT — Column table ═══════════════════════════════
    with left:
        if filtered.empty:
            st.caption("Aucune colonne ne correspond.")
        else:
            # Header row
            # hc = st.columns([3, 1.5, 3.5, 2, 1.8])
            hc = st.columns([3, 1.5, 3.5, 2, 1.8, 1])
            for col_w, lbl in zip(hc, ["Colonne","Type","Description","Contraintes","Complétude",""]):
                with col_w:
                    st.markdown(
                        f'<span style="font-size:.7rem;font-weight:700;color:#5a7290;'
                        f'text-transform:uppercase;letter-spacing:.06em">{lbl}</span>',
                        unsafe_allow_html=True,
                    )
            st.markdown(
                '<hr style="margin:4px 0 6px;border:none;border-top:1.5px solid #c8d8ec">',
                unsafe_allow_html=True,
            )

            for _, row in filtered.iterrows():
                col_name    = row["COLUMN_NAME"]
                selected    = st.session_state[ss_key] == col_name
                data_type   = row["DATA_TYPE"]
                description = str(row.get("DESCRIPTION","") or "").strip()
                nullable    = row.get("IS_NULLABLE","YES")
                ctypes      = str(row.get("CONSTRAINT_TYPES","") or "")
                dc_str      = _dot_class(col_name, latest_df, column_refs_map)
                dtype_cls, dtype_lbl = dtype_css(data_type)
                comp        = completeness_map.get(col_name)
                comp_c      = completeness_color(comp) if comp is not None else "#bdbdbd"
                dot_c       = _DOT_COLORS.get(dc_str, "#9e9e9e")
                badges      = _constraint_badges(nullable, ctypes)

                # Full-row highlight: coloured left border + background on active row
                border_style = "border-left:3px solid #1565c0;" if selected else "border-left:3px solid transparent;"
                row_bg_style = "background:#ddeeff;" if selected else ""
                st.markdown(
                    f'<div style="{row_bg_style}{border_style}border-radius:0 6px 6px 0;'
                    f'padding:1px 4px;margin-bottom:1px"></div>',
                    unsafe_allow_html=True,
                )

                rc = st.columns([3, 1.5, 3.5, 2, 1.8, 1])
                with rc[0]:
                    st.markdown(_strip_html(f"""
                        <div style="display:flex;align-items:center;gap:6px;padding:3px 0">
                            <span style="width:8px;height:8px;border-radius:50%;background:{dot_c};
                                         flex-shrink:0;display:inline-block;margin-top:1px"></span>
                            <span style="font-family:Consolas,monospace;font-size:.84rem;
                                         font-weight:600;color:#1a2a3a">{col_name}</span>
                        </div>
                    """), unsafe_allow_html=True)
                with rc[1]:
                    st.markdown(f'<span class="{dtype_cls}">{dtype_lbl}</span>',
                                unsafe_allow_html=True)
                with rc[2]:
                    short = (description[:50]+"…") if len(description) > 50 else (description or "—")
                    st.markdown(
                        f'<span style="font-size:.8rem;color:#5a7290">{short}</span>',
                        unsafe_allow_html=True,
                    )
                with rc[3]:
                    st.markdown(
                        badges or '<span style="color:#bdbdbd;font-size:.78rem">—</span>',
                        unsafe_allow_html=True,
                    )
                with rc[4]:
                    if comp is not None:
                        st.markdown(_strip_html(f"""
                            <div>
                                <div style="background:#e0e0e0;border-radius:3px;height:5px">
                                    <div style="width:{comp:.0f}%;height:5px;border-radius:3px;background:{comp_c}"></div>
                                </div>
                                <span style="font-size:.68rem;color:{comp_c};font-weight:600">{comp:.0f}%</span>
                            </div>
                        """), unsafe_allow_html=True)
                    else:
                        st.markdown('<span style="color:#bdbdbd;font-size:.78rem">—</span>',
                                    unsafe_allow_html=True)

                # Selection button — label hidden, use column name as key
                #if st.button(col_name, key=f"td_btn_{col_name}",
                #             use_container_width=True, help=f"Sélectionner {col_name}"):
                #    st.session_state[ss_key] = col_name
                #    st.rerun()
                with rc[5]:
                    if st.button("🔍", key=f"td_btn_{col_name}",
                                 use_container_width=True,
                                 help=f"Voir le détail de {col_name}"):
                        st.session_state[ss_key] = col_name
                        st.rerun()

                st.markdown(
                    '<div style="height:1px;background:#f0f5fb;margin:0 0 4px"></div>',
                    unsafe_allow_html=True,
                )

    # ══════════════════ RIGHT — Detail panel ══════════════════════════════
    with right:
        selected_col = st.session_state[ss_key]

        if selected_col is None:
            st.markdown(_strip_html("""
                <div class="col-placeholder" style="margin-top:60px">
                    <div style="font-size:2rem;margin-bottom:10px">←</div>
                    <div>Sélectionnez une colonne</div>
                    <div style="font-size:.8rem;margin-top:5px;color:#8aaac8">pour voir son profil</div>
                </div>
            """), unsafe_allow_html=True)
            return

        mrows = meta_df[meta_df["COLUMN_NAME"] == selected_col]
        if mrows.empty:
            st.info(f"Métadonnées introuvables pour `{selected_col}`.")
            return

        meta       = mrows.iloc[0]
        dtype_cls, dtype_lbl = dtype_css(meta["DATA_TYPE"])
        dc_str     = _dot_class(selected_col, latest_df, column_refs_map)
        dot_c      = _DOT_COLORS.get(dc_str, "#757575")
        dmf_lbl    = ("● FAILED" if dc_str == "fail"
                      else "● PASSED" if dc_str == "pass"
                      else "○ Aucune DMF")
        dmf_lbl_c  = dot_c

        # Header
        st.markdown(_strip_html(f"""
            <div style="padding:10px 14px;background:#f0f7ff;border-radius:10px;
                        margin-bottom:12px;border:1.5px solid #c8d8ec">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
                    <span style="width:10px;height:10px;border-radius:50%;background:{dot_c};
                                 flex-shrink:0;display:inline-block"></span>
                    <span style="font-family:Consolas,monospace;font-size:1rem;
                                 font-weight:700;color:#1a2a3a">{selected_col}</span>
                    <span class="{dtype_cls}">{meta['DATA_TYPE']}</span>
                </div>
                <span style="font-size:.76rem;color:{dmf_lbl_c};font-weight:600">{dmf_lbl}</span>
            </div>
        """), unsafe_allow_html=True)

        # 1. Metadata
        st.markdown('<div class="section-title">Métadonnées</div>', unsafe_allow_html=True)
        _section_metadata(meta, completeness_map)

        # 2. Data Profiling
        _section_profiling(session, db, schema, table,
                           selected_col, meta["DATA_TYPE"], completeness_map)

        # 3. DQ Rules — uses column_refs_map for accurate column→DMF matching
        _section_dq_rules(selected_col, latest_df, column_refs_map=column_refs_map)