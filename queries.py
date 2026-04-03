# ======================================================================================
# queries.py — All Snowflake SQL functions
#
# Rules:
#   - Every function is decorated with @st.cache_data
#   - Session is passed as _session (leading underscore = not included in cache key)
#   - Navigation lists: TTL 3600s (slow-changing)
#   - Metric data:      TTL 300s  (refreshed every 5 min)
#   - All SQL queries are plain SELECTs on Snowflake views — no CTEs, no JOINs
#     (complex logic lives in the 4 Snowflake views, see DMF_VIEWS_SNOWFLAKE.sql)
# ======================================================================================

import streamlit as st
import pandas as pd
from snowflake.snowpark import Session

from config import VIEW_DB, VIEW_SCHEMA


def _run_query(session: Session, sql: str) -> pd.DataFrame:
    """Execute a Snowpark SQL string and return a pandas DataFrame."""
    return session.sql(sql).to_pandas()


# ── Schema-level queries (Global View) ───────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_schema_table_scores(_session: Session, db: str, schema: str) -> pd.DataFrame:
    """
    Per-table quality scores for the selected schema.
    Source: VW_DQ_TABLE_SCORES — aggregated (TOTAL/CORE/CUSTOM DMFs,
    PASSED/FAILED checks, QUALITY_SCORE_PCT, LAST_CHECK_TIME).
    """
    sql = f"""
    SELECT
        TABLE_NAME,
        TOTAL_DMFS,
        CORE_DMFS,
        CUSTOM_DMFS,
        PASSED_CHECKS,
        FAILED_CHECKS,
        QUALITY_SCORE_PCT,
        LAST_CHECK_TIME
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_TABLE_SCORES
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
    ORDER BY QUALITY_SCORE_PCT ASC NULLS LAST, TABLE_NAME
    """
    return _run_query(_session, sql)


# ── Table-level queries (Detailed View) ──────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_table_dmf_results(_session: Session, db: str, schema: str, table: str) -> pd.DataFrame:
    """
    Latest status of each DMF deployed on the selected table.

    Enriched with column-level information from DATA_METRIC_FUNCTION_REFERENCES
    to distinguish the same DMF deployed on multiple columns (Bug 2/3 fix).

    Returns one row per (DMF_NAME, REF_COLUMN_NAME).
    REF_COLUMN_NAME is NULL when a DMF has no specific column argument (e.g. ROW_COUNT).
    Falls back to VW_DQ_LATEST_RESULTS alone when DATA_METRIC_FUNCTION_REFERENCES
    is unavailable (access error) — in that case REF_COLUMN_NAME is always NULL.
    """
    # Primary: latest results from the view
    sql_results = f"""
    SELECT
        DMF_NAME,
        DMF_TYPE,
        ISSUES_FOUND,
        LAST_CHECKED,
        DMF_RULE,
        STATUS
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_LATEST_RESULTS
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
      AND TABLE_NAME     = '{table}'
    ORDER BY DMF_TYPE, STATUS, DMF_NAME
    """
    results_df = _run_query(_session, sql_results)
    if results_df.empty:
        return results_df

    # Secondary: column refs — one row per (DMF, column)
    # REF_ENTITY_NAME must be a 2-part name (schema.table), NOT the 3-part
    # fully-qualified form (db.schema.table) — Snowflake raises SQL error otherwise.
    col_refs_sql = f"""
    SELECT
        UPPER(f.value::STRING)      AS REF_COLUMN_NAME,
        UPPER(refs.METRIC_NAME)     AS DMF_NAME
    FROM TABLE(
        {db}.INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
            REF_ENTITY_NAME   => '{schema}.{table}',
            REF_ENTITY_DOMAIN => 'table'
        )
    ) AS refs,
    LATERAL FLATTEN(input => refs.REF_COLUMN_NAMES) AS f
    ORDER BY refs.METRIC_NAME, f.value
    """
    try:
        refs_df = _run_query(_session, col_refs_sql)
    except Exception:
        refs_df = pd.DataFrame(columns=["REF_COLUMN_NAME", "DMF_NAME"])

    if refs_df.empty:
        results_df["REF_COLUMN_NAME"] = None
        return results_df

    # Normalise column names to uppercase before merge — Snowpark may lowercase them
    results_df.columns = [c.upper() for c in results_df.columns]
    refs_df.columns    = [c.upper() for c in refs_df.columns]

    # Left-join: results × column refs → one row per (DMF, column)
    merged = results_df.merge(refs_df, on="DMF_NAME", how="left")
    return merged.sort_values(
        ["DMF_TYPE", "STATUS", "DMF_NAME", "REF_COLUMN_NAME"],
        na_position="last",
    )



@st.cache_data(ttl=300, show_spinner=False)
def get_table_dmf_column_refs(
    _session: Session, db: str, schema: str, table: str
) -> pd.DataFrame:
    """
    Column-level DMF associations for the selected table.
    Source: INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES table function.

    Returns one row per (DMF_NAME, REF_COLUMN_NAME) combination, enabling:
      - Bug 2 fix: distinguish the same DMF deployed on multiple columns
      - Bug 3 fix: accurate column → DMF mapping in Table Detail panel

    REF_COLUMN_NAMES is a VARIANT (array) — FLATTEN produces one row per column.
    Requires the DATA_METRIC_USER database role.
    Falls back to an empty DataFrame silently on access error.
    """
    sql = f"""
    SELECT
        UPPER(f.value::STRING)         AS REF_COLUMN_NAME,
        UPPER(refs.METRIC_NAME)        AS DMF_NAME,
        refs.METRIC_DATABASE           AS METRIC_DATABASE,
        refs.METRIC_SCHEMA             AS METRIC_SCHEMA,
        refs.METRIC_FUNCTION_STATUS    AS DMF_STATUS
    FROM TABLE(
        {db}.INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
            REF_ENTITY_NAME   => '{schema}.{table}',
            REF_ENTITY_DOMAIN => 'table'
        )
    ) AS refs,
    LATERAL FLATTEN(input => refs.REF_COLUMN_NAMES) AS f
    ORDER BY refs.METRIC_NAME, f.value
    """
    try:
        df = _run_query(_session, sql)
        if not df.empty:
            df.columns = [c.upper() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "REF_COLUMN_NAME", "DMF_NAME", "METRIC_DATABASE",
            "METRIC_SCHEMA", "DMF_STATUS"
        ])


@st.cache_data(ttl=300, show_spinner=False)
def get_table_dmf_trend(
    _session: Session, db: str, schema: str, table: str, hours: int = 24
) -> pd.DataFrame:
    """
    Hourly DMF value trend over the selected time window.
    Source: VW_DQ_ENRICHED_RESULTS — aggregated by hour.
    The `hours` parameter makes a static Snowflake view impractical here.
    """
    sql = f"""
    SELECT
        DATE_TRUNC('HOUR', MEASUREMENT_TIME)  AS MEASUREMENT_HOUR,
        METRIC_NAME,
        AVG(VALUE)                            AS AVG_VALUE,
        MAX(VALUE)                            AS MAX_VALUE,
        COUNT(*)                              AS MEASUREMENT_COUNT
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_ENRICHED_RESULTS
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
      AND TABLE_NAME     = '{table}'
      AND MEASUREMENT_TIME >= DATEADD(HOUR, -{hours}, CURRENT_TIMESTAMP())
    GROUP BY 1, 2
    ORDER BY 1 DESC, 2
    """
    return _run_query(_session, sql)


@st.cache_data(ttl=300, show_spinner=False)
def get_table_execution_history(
    _session: Session, db: str, schema: str, table: str, limit: int = 500
) -> pd.DataFrame:
    """
    Full DMF execution log for the selected table (most recent first).
    Source: VW_DQ_ENRICHED_RESULTS — all executions with STATUS pre-computed.
    """
    sql = f"""
    SELECT
        MEASUREMENT_TIME,
        METRIC_NAME,
        VALUE,
        DMF_RULE        AS EXPECTATION_EXPRESSION,
        STATUS,
        TABLE_NAME
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_ENRICHED_RESULTS
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
      AND TABLE_NAME     = '{table}'
    ORDER BY MEASUREMENT_TIME DESC
    LIMIT {limit}
    """
    return _run_query(_session, sql)


# ── Table Detail tab queries ──────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_table_column_metadata(
    _session: Session, db: str, schema: str, table: str
) -> pd.DataFrame:
    """
    Column metadata from INFORMATION_SCHEMA.COLUMNS only.
    Requires standard SELECT privilege — no elevated grants needed.

    CONSTRAINT_TYPES is left empty here and enriched separately by
    get_column_pk_unique_constraints(), which degrades gracefully on
    access errors (KEY_COLUMN_USAGE requires elevated privileges in SiS).
    """
    sql = f"""
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        ORDINAL_POSITION,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        COLUMN_DEFAULT,
        COALESCE(COMMENT, '') AS DESCRIPTION,
        ''                    AS CONSTRAINT_TYPES
    FROM {db}.INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_CATALOG = '{db}'
      AND TABLE_SCHEMA  = '{schema}'
      AND TABLE_NAME    = '{table}'
    ORDER BY ORDINAL_POSITION
    """
    return _run_query(_session, sql)


@st.cache_data(ttl=3600, show_spinner=False)
def get_column_pk_unique_constraints(
    _session: Session, db: str, schema: str, table: str
) -> dict:
    """
    Attempt to fetch PRIMARY KEY / UNIQUE constraints per column.

    Requires INFORMATION_SCHEMA.KEY_COLUMN_USAGE — needs elevated privileges
    (MANAGE GRANTS / ACCOUNTADMIN) not always available in SiS.
    Returns {} silently on any access error so the UI degrades gracefully
    (only the NN badge from IS_NULLABLE will be shown).
    """
    try:
        sql = f"""
        SELECT
            kcu.COLUMN_NAME,
            LISTAGG(tc.CONSTRAINT_TYPE, ',')
                WITHIN GROUP (ORDER BY tc.CONSTRAINT_TYPE) AS CONSTRAINT_TYPES
        FROM {db}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN {db}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON  tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            AND tc.TABLE_SCHEMA    = kcu.TABLE_SCHEMA
            AND tc.TABLE_NAME      = kcu.TABLE_NAME
        WHERE tc.TABLE_SCHEMA    = '{schema}'
          AND tc.TABLE_NAME      = '{table}'
          AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE')
        GROUP BY kcu.COLUMN_NAME
        """
        df = _run_query(_session, sql)
        if df.empty:
            return {}
        return dict(zip(df["COLUMN_NAME"], df["CONSTRAINT_TYPES"]))
    except Exception:
        return {}   # Degrade silently — UI shows only NN badge


# Keep backward-compatible alias
get_table_columns = get_table_column_metadata


@st.cache_data(ttl=300, show_spinner=False)
def get_all_columns_completeness(
    _session: Session,
    db: str,
    schema: str,
    table: str,
    column_names: tuple,          # tuple (hashable) so st.cache_data can cache it
) -> dict:
    """
    Compute completeness % for ALL columns in a SINGLE table scan.

    Returns a dict {column_name: completeness_pct}.
    Limited to the first 200 columns to keep SQL length reasonable.
    Requires SELECT privilege on the table.
    """
    cols = list(column_names[:200])
    if not cols:
        return {}
    clauses = ",\n    ".join(
        f'COUNT("{c}") * 100.0 / NULLIF(COUNT(*), 0) AS "{c}"'
        for c in cols
    )
    sql = f"SELECT\n    {clauses}\nFROM {db}.{schema}.{table}"
    try:
        df = _run_query(_session, sql)
        if df.empty:
            return {c: 0.0 for c in cols}
        row = df.iloc[0]
        return {c: float(row[c]) if pd.notna(row[c]) else 0.0 for c in cols}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_column_profiling_extended(
    _session: Session,
    db: str,
    schema: str,
    table: str,
    column: str,
    is_numeric: bool,
    is_text: bool,
) -> pd.DataFrame:
    """
    Extended single-column profile:
      Text columns  : MIN_LENGTH, MAX_LENGTH, AVG_LENGTH
      Numeric columns: MEAN_VAL, STD_VAL, OUTLIER_COUNT (3-sigma rule)

    Outlier detection uses a CTE to avoid correlated aggregate expressions.
    Requires SELECT privilege on the table.
    """
    if is_text:
        sql = f"""
        SELECT
            MIN(LENGTH("{column}"))                AS MIN_LENGTH,
            MAX(LENGTH("{column}"))                AS MAX_LENGTH,
            ROUND(AVG(LENGTH("{column}")), 1)      AS AVG_LENGTH,
            NULL                                   AS MEAN_VAL,
            NULL                                   AS STD_VAL,
            NULL                                   AS OUTLIER_COUNT
        FROM {db}.{schema}.{table}
        WHERE "{column}" IS NOT NULL
        """
    elif is_numeric:
        sql = f"""
        WITH stats AS (
            SELECT
                AVG("{column}")    AS m,
                STDDEV("{column}") AS s
            FROM {db}.{schema}.{table}
            WHERE "{column}" IS NOT NULL
        ),
        outliers AS (
            SELECT COUNT(*) AS cnt
            FROM {db}.{schema}.{table}, stats
            WHERE "{column}" IS NOT NULL
              AND ("{column}" < stats.m - 3 * stats.s
                   OR "{column}" > stats.m + 3 * stats.s)
        )
        SELECT
            NULL              AS MIN_LENGTH,
            NULL              AS MAX_LENGTH,
            NULL              AS AVG_LENGTH,
            ROUND(stats.m, 4) AS MEAN_VAL,
            ROUND(stats.s, 4) AS STD_VAL,
            outliers.cnt      AS OUTLIER_COUNT
        FROM stats, outliers
        """
    else:
        # Date / Boolean / other: no meaningful length or numeric stats
        sql = f"""
        SELECT NULL AS MIN_LENGTH, NULL AS MAX_LENGTH, NULL AS AVG_LENGTH,
               NULL AS MEAN_VAL,   NULL AS STD_VAL,   NULL AS OUTLIER_COUNT
        """
    return _run_query(_session, sql)


@st.cache_data(ttl=300, show_spinner=False)
def get_column_profile(
    _session: Session,
    db: str,
    schema: str,
    table: str,
    column: str,
    is_numeric: bool,
) -> pd.DataFrame:
    """
    Profile statistics for a single column: completeness, cardinality, min/max/avg.
    Runs directly on the monitored table — requires SELECT privilege.

    Snowflake casting rules that drove these choices:
      - TRY_CAST is ONLY valid when the SOURCE is a string (VARCHAR/TEXT).
        Using TRY_CAST(number_col AS FLOAT) raises a compilation error because the
        source is already a NUMBER, not a string.  → We use AVG(col) directly.
      - TO_CHAR() works universally for all scalar types as the *target* (number,
        date, timestamp, boolean …) and replaces any cast-to-VARCHAR pattern.
      - AVG() is a native aggregate for any numeric type; no cast needed.
        For non-numeric columns, AVG_VAL is NULL.
    """
    # AVG: call the column directly — Snowflake resolves AVG for all numeric types
    # without any explicit cast.  TRY_CAST(numeric_col AS FLOAT) is NOT supported
    # because TRY_CAST only accepts a string source in Snowflake.
    avg_clause = f'AVG("{column}")' if is_numeric else "NULL"

    sql = f"""
    SELECT
        COUNT(*)                    AS TOTAL_ROWS,
        COUNT("{column}")           AS NON_NULL_COUNT,
        COUNT(DISTINCT "{column}")  AS DISTINCT_COUNT,
        TO_CHAR(MIN("{column}"))    AS MIN_VAL,
        TO_CHAR(MAX("{column}"))    AS MAX_VAL,
        {avg_clause}                AS AVG_VAL
    FROM {db}.{schema}.{table}
    """
    return _run_query(_session, sql)


@st.cache_data(ttl=300, show_spinner=False)
def get_column_top_values(
    _session: Session,
    db: str,
    schema: str,
    table: str,
    column: str,
    limit: int = 8,
) -> pd.DataFrame:
    """
    Top N non-null values by frequency for the selected column.
    Requires SELECT privilege on the table.

    TO_CHAR() is used instead of TRY_CAST(...AS VARCHAR) because Snowflake
    does not support TRY_CAST to VARCHAR — it raises a compilation error for
    non-TEXT source types (DATE, NUMBER, TIMESTAMP, BOOLEAN, etc.).
    TO_CHAR() works universally for all scalar Snowflake types.
    """
    sql = f"""
    SELECT
        TO_CHAR("{column}")  AS VALUE,
        COUNT(*)             AS CNT
    FROM {db}.{schema}.{table}
    WHERE "{column}" IS NOT NULL
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT {limit}
    """
    return _run_query(_session, sql)



# ── DQ Platform DMF catalog ───────────────────────────────────────────────────
# Functions tagged with {"dq_solution":"DQ_PLATFORM",...} in their COMMENT.
# Parsed via TRY_PARSE_JSON — returns {} silently if COMMENT is absent or
# the function is not managed by the platform (CORE DMFs, untagged CUSTOM DMFs).

@st.cache_data(ttl=3600, show_spinner=False)
def get_custom_dmf_catalog(_session: Session, db: str) -> pd.DataFrame:
    """
    Read the DQ Platform DMF catalog from INFORMATION_SCHEMA.FUNCTIONS.

    Only returns functions whose COMMENT contains the tag:
        {"dq_solution":"DQ_PLATFORM", ...}

    Parsed fields:
      TECH_NAME   : FUNCTION_NAME (Snowflake identifier)
      BUS_NAME    : dq_busname   (display name shown in the UI)
      DIMENSION   : dq_dimension (one of: VALIDITY/ACCURACY/CONSISTENCY/
                                   COMPLETENESS/FRESHNESS/UNIQUENESS)
      DESCRIPTION : dq_description
      OWNER       : owner
      VERSION     : version

    TTL 3600s — function metadata changes only on CREATE OR REPLACE.
    """
    sql = f"""
    SELECT
        FUNCTION_NAME                                              AS TECH_NAME,
        UPPER(FUNCTION_SCHEMA)                                     AS FUNCTION_SCHEMA,
        COALESCE(
            TRY_PARSE_JSON(COMMENT):dq_busname::STRING,
            FUNCTION_NAME
        )                                                          AS BUS_NAME,
        UPPER(COALESCE(
            TRY_PARSE_JSON(COMMENT):dq_dimension::STRING,
            'VALIDITY'
        ))                                                         AS DIMENSION,
        COALESCE(TRY_PARSE_JSON(COMMENT):dq_description::STRING, '') AS DESCRIPTION,
        COALESCE(TRY_PARSE_JSON(COMMENT):owner::STRING,          '') AS OWNER,
        COALESCE(TRY_PARSE_JSON(COMMENT):version::STRING,        '') AS VERSION
    FROM {db}.INFORMATION_SCHEMA.FUNCTIONS
    WHERE IS_DATA_METRIC = 'YES'
      AND TRY_PARSE_JSON(COMMENT):dq_solution::STRING = 'DQ_PLATFORM'
    ORDER BY TECH_NAME
    """
    try:
        return _run_query(_session, sql)
    except Exception:
        return pd.DataFrame(columns=[
            "TECH_NAME","FUNCTION_SCHEMA","BUS_NAME","DIMENSION",
            "DESCRIPTION","OWNER","VERSION"
        ])


@st.cache_data(ttl=300, show_spinner=False)
def get_schema_latest_dmf_results(_session: Session, db: str, schema: str) -> pd.DataFrame:
    """
    Latest DMF result for every (table, metric) pair in the selected schema.
    Used in the Global View to compute per-dimension quality scores.
    Source: VW_DQ_LATEST_RESULTS — one row per table × metric, most recent only.
    """
    sql = f"""
    SELECT
        TABLE_NAME,
        DMF_NAME,
        DMF_TYPE,
        STATUS,
        ISSUES_FOUND,
        LAST_CHECKED
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_LATEST_RESULTS
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
    ORDER BY TABLE_NAME, DMF_NAME
    """
    return _run_query(_session, sql)


# ── Navigation queries (Sidebar selectors) ────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_databases(_session: Session) -> list[str]:
    """Databases that have at least one monitored table. TTL 1h."""
    sql = f"""
    SELECT DISTINCT TABLE_DATABASE
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_MONITORED_TABLES
    ORDER BY TABLE_DATABASE
    """
    df = _run_query(_session, sql)
    return df["TABLE_DATABASE"].tolist() if not df.empty else []


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_schemas(_session: Session, db: str) -> list[str]:
    """Schemas with monitored tables in the selected database. TTL 1h."""
    sql = f"""
    SELECT DISTINCT TABLE_SCHEMA
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_MONITORED_TABLES
    WHERE TABLE_DATABASE = '{db}'
    ORDER BY TABLE_SCHEMA
    """
    df = _run_query(_session, sql)
    return df["TABLE_SCHEMA"].tolist() if not df.empty else []


@st.cache_data(ttl=3600, show_spinner=False)
def get_monitored_tables(_session: Session, db: str, schema: str) -> list[str]:
    """Monitored BASE TABLEs in the selected database + schema. TTL 1h."""
    sql = f"""
    SELECT TABLE_NAME
    FROM {VIEW_DB}.{VIEW_SCHEMA}.VW_DQ_MONITORED_TABLES
    WHERE TABLE_DATABASE = '{db}'
      AND TABLE_SCHEMA   = '{schema}'
    ORDER BY TABLE_NAME
    """
    df = _run_query(_session, sql)
    return df["TABLE_NAME"].tolist() if not df.empty else []