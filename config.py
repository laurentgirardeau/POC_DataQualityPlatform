# ======================================================================================
# config.py — Constants and CSS styles
# All configuration lives here. One place to change, everywhere updated.
# ======================================================================================

# ── Chart theme ───────────────────────────────────────────────────────────────────────
CHART_FONT_COLOR = "#1a2a3a"
CHART_GRID_COLOR = "#d8e6f3"
CHART_BG         = "rgba(0,0,0,0)"
CHART_PLOT_BG    = "#f8fbff"

# ── Sidebar defaults ──────────────────────────────────────────────────────────────────
DEFAULT_DB     = "DB_DATA_QUALITY_PRODUCT_SANDBOX"
DEFAULT_SCHEMA = "DATA_QUALITY"

# ── Snowflake views location (see DMF_VIEWS_SNOWFLAKE.sql) ───────────────────────────
VIEW_DB     = "DB_DATA_QUALITY_PRODUCT_SANDBOX"
VIEW_SCHEMA = "DATA_QUALITY"

# ── Status → color (single source of truth used across all visuals) ──────────────────
STATUS_COLORS: dict[str, str] = {
    "PASSED":  "#2e7d32",
    "FAILED":  "#c62828",
    "NO_DATA": "#757575",
    "UNKNOWN": "#e65100",
}

# ── CSS styles — injected once at startup by streamlit_app.py ────────────────────────
CSS_STYLES = """
<style>
  :root {
    --bg:         #f0f5fb;
    --surface:    #ffffff;
    --surface-2:  #e8f0f9;
    --border:     #c8d8ec;
    --accent:     #1565c0;
    --accent-lt:  #42a5f5;
    --success:    #2e7d32;
    --warning:    #e65100;
    --danger:     #c62828;
    --text:       #1a2a3a;
    --text-muted: #5a7290;
  }

  /* ── Layout ──────────────────────────────────────────────────────────── */
  .stApp { background-color: var(--bg); color: var(--text); }
  .block-container {
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
  }
  h1, h2, h3 { color: var(--accent) !important; }

  /* ── Sidebar ──────────────────────────────────────────────────────────── */
  section[data-testid="stSidebar"] {
    background: var(--surface-2);
    border-right: 2px solid var(--border);
  }
  section[data-testid="stSidebar"] * { color: var(--text) !important; }

  /* ── KPI cards ───────────────────────────────────────────────────────── */
  .kpi-card {
    background: var(--surface); border: 1.5px solid var(--border);
    border-radius: 10px; padding: 11px 14px; text-align: center;
    box-shadow: 0 1px 5px rgba(21,101,192,.07);
    transition: box-shadow .2s, border-color .2s;
  }
  .kpi-card:hover {
    border-color: var(--accent-lt);
    box-shadow: 0 3px 12px rgba(21,101,192,.13);
  }
  .kpi-value { font-size: 1.45rem; font-weight: 700; line-height: 1.15; }
  .kpi-label {
    font-size: .68rem; color: var(--text-muted); margin-top: 4px;
    letter-spacing: .06em; text-transform: uppercase; font-weight: 600;
  }
  .kpi-delta { font-size: .75rem; margin-top: 3px; }

  /* ── Status & type badges ────────────────────────────────────────────── */
  .badge-pass   { background:#e8f5e9; color:var(--success); padding:3px 12px;
                  border-radius:20px; font-size:.8rem; font-weight:600;
                  border:1px solid #a5d6a7; white-space:nowrap; }
  .badge-fail   { background:#ffebee; color:var(--danger); padding:3px 12px;
                  border-radius:20px; font-size:.8rem; font-weight:600;
                  border:1px solid #ef9a9a; white-space:nowrap; }
  .badge-warn   { background:#fff3e0; color:var(--warning); padding:3px 12px;
                  border-radius:20px; font-size:.8rem; font-weight:600;
                  border:1px solid #ffcc80; white-space:nowrap; }
  .badge-nodata { background:#f5f5f5; color:#757575; padding:3px 12px;
                  border-radius:20px; font-size:.8rem; font-weight:600;
                  border:1px solid #bdbdbd; white-space:nowrap; }
  .badge-core   { background:#e3f2fd; color:#1565c0; padding:2px 10px;
                  border-radius:20px; font-size:.75rem; font-weight:700;
                  border:1px solid #90caf9; white-space:nowrap; }
  .badge-custom { background:#f3e5f5; color:#6a1b9a; padding:2px 10px;
                  border-radius:20px; font-size:.75rem; font-weight:700;
                  border:1px solid #ce93d8; white-space:nowrap; }

  /* ── Column constraint badges (Table Detail) ─────────────────────────── */
  .badge-pk { background:#fff8e1; color:#f57f17; padding:1px 7px; border-radius:5px;
              font-size:.7rem; font-weight:800; border:1px solid #ffcc02; white-space:nowrap; }
  .badge-nn { background:#fce4ec; color:#c62828; padding:1px 7px; border-radius:5px;
              font-size:.7rem; font-weight:800; border:1px solid #ef9a9a; white-space:nowrap; }
  .badge-uq { background:#e8f5e9; color:#2e7d32; padding:1px 7px; border-radius:5px;
              font-size:.7rem; font-weight:800; border:1px solid #a5d6a7; white-space:nowrap; }

  /* ── Global metrics strip (Table Detail top) ─────────────────────────── */
  .td-metrics-strip {
    display:flex; gap:24px; align-items:center;
    background:var(--surface); border:1.5px solid var(--border);
    border-radius:10px; padding:12px 20px; margin-bottom:14px;
  }
  .td-metric-val  { font-size:1.4rem; font-weight:700; color:var(--accent); line-height:1; }
  .td-metric-lbl  { font-size:.72rem; color:var(--text-muted); text-transform:uppercase;
                    letter-spacing:.05em; margin-top:2px; }
  .td-metric-sep  { width:1px; height:36px; background:var(--border); }

  /* ── Column row (Table Detail left panel) ───────────────────────────────*/
  .col-row {
    display:flex; align-items:center; gap:10px; padding:8px 12px;
    border-radius:7px; margin-bottom:3px; border:1.5px solid transparent;
    transition:background .12s, border-color .12s;
  }
  .col-row:hover  { background:#f0f7ff; border-color:var(--accent-lt); }
  .col-row.active { background:#e3f2fd; border-color:var(--accent);   }
  .col-row-name   { font-family:Consolas,monospace; font-size:.86rem; font-weight:600;
                    color:var(--text); min-width:0; flex:2; overflow:hidden;
                    text-overflow:ellipsis; white-space:nowrap; }
  .col-row-desc   { font-size:.8rem; color:var(--text-muted); flex:3; overflow:hidden;
                    text-overflow:ellipsis; white-space:nowrap; min-width:0; }
  .col-row-badges { display:flex; gap:4px; flex-shrink:0; }
  .col-row-comp   { min-width:60px; flex-shrink:0; }

  /* ── Right panel — DQ rule card ─────────────────────────────────────────*/
  .dq-rule-card {
    border:1.5px solid var(--border); border-radius:10px;
    padding:12px 16px; margin-bottom:10px; background:var(--surface);
  }
  .dq-rule-card-header {
    display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;
  }
  .dq-rule-name  { font-family:Consolas,monospace; font-weight:700;
                   font-size:.9rem; color:var(--text); }
  .dq-dimension  { font-size:.72rem; font-weight:600; padding:2px 8px;
                   border-radius:10px; background:var(--surface-2);
                   color:var(--text-muted); white-space:nowrap; }
  .dq-rule-meta  { font-size:.8rem; color:var(--text-muted); }

  /* ── Right panel — metadata cards ────────────────────────────────────── */
  .meta-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px; }
  .meta-card { background:var(--surface-2); border-radius:8px; padding:8px 12px; }
  .meta-card-label { font-size:.68rem; text-transform:uppercase; letter-spacing:.06em;
                     color:var(--text-muted); margin-bottom:3px; font-weight:600; }
  .meta-card-value { font-size:.88rem; color:var(--text); font-weight:500; word-break:break-all; }

  /* ── Section headings ────────────────────────────────────────────────── */
  .section-title {
    font-size: 1rem; font-weight: 600; color: var(--accent);
    border-left: 3px solid var(--accent-lt); padding-left: 10px;
    margin: 20px 0 10px; letter-spacing: .01em;
  }

  /* ── Page header banner ──────────────────────────────────────────────── */
  .page-header {
    background: linear-gradient(135deg,#1565c0 0%,#1e88e5 60%,#42a5f5 100%);
    border-radius: 12px; padding: 18px 24px; margin-bottom: 20px;
  }
  .page-header h2 { color: #fff !important; margin: 0 0 4px; font-size: 1.4rem; }
  .page-header p  { color: rgba(255,255,255,.85) !important; margin: 0; font-size: .9rem; }

  /* ── DMF table — scrollable, no word-wrap ────────────────────────────── */
  .dq-table-wrapper { width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .dq-table {
    width:100%; min-width:max-content; border-collapse:collapse;
    background:var(--surface); border-radius:10px; overflow:hidden;
    box-shadow:0 1px 4px rgba(21,101,192,.08);
  }
  .dq-table thead tr {
    background:var(--surface-2); color:var(--text-muted);
    font-size:.78rem; letter-spacing:.05em; text-transform:uppercase;
  }
  .dq-table thead th { padding:10px 16px; font-weight:600; white-space:nowrap; }
  .dq-table tbody tr { border-bottom:1px solid var(--border); }
  .dq-table tbody tr:hover { background:#f0f7ff; }
  .dq-table tbody td { padding:9px 16px; color:var(--text); font-size:.88rem; white-space:nowrap; }

  /* ── Score bar (Global View per-table table) ─────────────────────────── */
  .score-bar-bg  { background:#e0e0e0; border-radius:6px; height:8px; width:100%; min-width:80px; }
  .score-bar-fill { height:8px; border-radius:6px; }

  /* ── Refresh button ──────────────────────────────────────────────────── */
  div[data-testid="stButton"] > button {
    background:var(--accent); color:#fff; border:none; border-radius:8px; font-weight:600;
  }
  div[data-testid="stButton"] > button:hover { background:#1976d2; }

  /* ── Table Detail — column list pills ───────────────────────────────── */
  .col-pill {
    display:flex; align-items:center; gap:8px; padding:8px 12px; margin-bottom:6px;
    border:1.5px solid var(--border); border-radius:8px; background:var(--surface);
    cursor:pointer; transition:border-color .15s, background .15s;
  }
  .col-pill:hover { border-color:var(--accent-lt); background:#e3f2fd; }
  .col-dot { width:9px; height:9px; border-radius:50%; flex-shrink:0; }
  .col-dot.pass   { background:var(--success); }
  .col-dot.fail   { background:var(--danger); }
  .col-dot.nodata { background:var(--text-muted); }
  .col-name { font-family:Consolas,monospace; font-size:.88rem; color:var(--text); font-weight:500; flex:1; }

  /* ── Data type mini-badges (Table Detail) ────────────────────────────── */
  .dt-text   { background:#e3f2fd; color:#1565c0; padding:1px 7px; border-radius:10px; font-size:.72rem; font-weight:700; white-space:nowrap; }
  .dt-number { background:#e8f5e9; color:#2e7d32; padding:1px 7px; border-radius:10px; font-size:.72rem; font-weight:700; white-space:nowrap; }
  .dt-date   { background:#fff3e0; color:#e65100; padding:1px 7px; border-radius:10px; font-size:.72rem; font-weight:700; white-space:nowrap; }
  .dt-bool   { background:#f3e5f5; color:#6a1b9a; padding:1px 7px; border-radius:10px; font-size:.72rem; font-weight:700; white-space:nowrap; }
  .dt-other  { background:#f5f5f5; color:#616161; padding:1px 7px; border-radius:10px; font-size:.72rem; font-weight:700; white-space:nowrap; }

  /* ── Column detail panel ────────────────────────────────────────────── */
  .col-placeholder {
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    height:300px; border:2px dashed var(--border); border-radius:12px;
    color:var(--text-muted); font-size:1rem;
  }
  .completeness-bar-bg  { background:#e0e0e0; border-radius:6px; height:10px; width:100%; margin:6px 0; }
  .completeness-bar     { height:10px; border-radius:6px; }
  .stat-card {
    background:var(--surface); border:1.5px solid var(--border);
    border-radius:10px; padding:12px 16px; text-align:center;
    box-shadow:0 1px 4px rgba(21,101,192,.06);
  }
  .stat-val   { font-size:1.4rem; font-weight:700; color:var(--accent); line-height:1.2; }
  .stat-label { font-size:.72rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.05em; margin-top:3px; }
  .dmf-card {
    background:var(--surface); border:1.5px solid var(--border);
    border-radius:8px; padding:10px 14px; margin-bottom:8px;
  }

  /* ── Dimension score cards — same rhythm as .kpi-card ───────────────── */
  .dim-score-grid {
    display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 14px;
  }
  .dim-score-card {
    flex:1; min-width:90px; border-radius:10px; padding:10px 12px;
    border:1.5px solid transparent; text-align:center;
    box-shadow:0 1px 4px rgba(0,0,0,.07);
    transition: box-shadow .2s, border-color .2s;
  }
  .dim-score-card:hover {
    box-shadow:0 2px 8px rgba(0,0,0,.13);
  }
  .dim-score-val  { font-size:1.45rem; font-weight:700; line-height:1.15; }
  .dim-score-name { font-size:.68rem; font-weight:700; text-transform:uppercase;
                    letter-spacing:.06em; margin-top:4px; }
  .dim-score-sub  { font-size:.68rem; margin-top:2px; opacity:.8; }

  footer { visibility:hidden; }
</style>
"""