"""
INE MCP Server

Exposes the Spanish National Statistics Institute (INE) Tempus3 JSON API
through the Model Context Protocol so that LLM assistants can discover,
explore, and retrieve official Spanish statistical data.

Data hierarchy
--------------
Operations  →  statistical domains (e.g. IPC, EPA, Censo)
  Tables    →  pre-defined cross-tabulations within an operation
    Groups  →  selection dimensions (geography, gender, age-band, …)
      Values→  the choices available for each dimension
  Series    →  individual time series (atomic data unit)
    Data    →  observations over time

Typical workflow
----------------
1. list_operations()                    # discover available domains
2. list_tables("IPC")                   # tables for the CPI operation
3. get_table_structure(50913)           # understand which filters exist
4. get_table_data(50913, last_n=3, …)  # retrieve the actual numbers
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ine_mcp.client import INEClient


# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "INE Statistics",
    instructions="""
You are connected to the Spanish National Statistics Institute (INE) API —
the primary source of official statistical data for Spain.

KEY CONCEPTS
  • Operations  – statistical domains (short codes like IPC, EPA, Censo…)
  • Tables      – pre-built cross-tabulations within an operation; each has
                  a numeric ID and selectable filter dimensions (groups).
  • Groups      – selection dimensions such as geography, gender, age-band.
  • Values      – concrete choices for each dimension (e.g. province names).
  • Series      – individual time series; the atomic unit that carries data.
  • Data points – numeric observations indexed by period.

RECOMMENDED WORKFLOW
  1. list_operations()              → find the relevant operation code
  2. list_tables("IPC")            → find the right table ID
  3. get_table_structure(50913)    → learn which filter dimensions exist
  4. get_table_data(50913, …)      → pull the actual numbers

  For ad-hoc cross-operation queries:
  5. get_operation_variables("IPC") → list variable IDs
  6. get_variable_values(762, "IPC") → list value IDs for a variable
  7. search_operation_data("IPC", filters=[("762","304092")], …)

LANGUAGE
  Pass lang="EN" for English labels, lang="ES" for Spanish (default "EN").

PERIODS
  Use ISO-style dates: "20240101" (1 Jan 2024).
  last_n gives the most-recent N periods without needing exact dates.
""",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _client(lang: str = "EN") -> INEClient:
    return INEClient(lang=lang)


def _trim(text: str, max_len: int = 120) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _safe_name(obj: Any) -> str:
    """Extract a human-readable name from a Tempus3 name field."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("Nombre", obj.get("nombre", str(obj)))
    return str(obj)


# The Any import is needed for the helper above but not declared in __future__
from typing import Any  # noqa: E402  (placed after helpers that use it)


# ---------------------------------------------------------------------------
# Tools — Operations
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_operations(
    geo: Optional[int] = None,
    lang: str = "EN",
) -> str:
    """
    List all statistical operations available in the INE Tempus3 database.

    Each operation is a statistical domain (e.g. IPC=Consumer Price Index,
    EPA=Labour Force Survey, Censo=Population Census).  Use the returned
    operation codes as input to the other tools.

    Args:
        geo:  Optional filter.  1 = only operations with geographic
              breakdowns (regions/provinces/municipalities).
              0 = only nationwide operations.  Omit for all.
        lang: Response language — "EN" (English) or "ES" (Spanish).

    Returns:
        JSON array of operations, each with:
          id       – numeric Tempus3 ID
          code     – short alphabetic code (use this in other tools)
          ioe_code – Inventory of Statistical Operations code
          name     – human-readable operation name
    """
    async with _client(lang) as c:
        ops = await c.get_operations(geo=geo)

    result = [
        {
            "id": op.get("Id"),
            "code": op.get("Codigo"),
            "ioe_code": f"IOE{op.get('Cod_IOE', '')}",
            "name": _safe_name(op.get("Nombre", "")),
        }
        for op in (ops if isinstance(ops, list) else [ops])
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_operation(operation: str, lang: str = "EN") -> str:
    """
    Return detailed metadata for a single statistical operation.

    Args:
        operation: Operation code (e.g. "IPC") or numeric ID.
        lang:      "EN" or "ES".

    Returns:
        JSON object with full operation metadata including periodicities,
        subject area, and links to related resources.
    """
    async with _client(lang) as c:
        data = await c.get_operation(operation)
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools — Tables
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_tables(operation: str, lang: str = "EN") -> str:
    """
    List all statistical tables for a given operation.

    Tables are pre-built cross-tabulations (think: spreadsheet tabs).
    Each table has a numeric ID used for fetching its structure and data.

    Args:
        operation: Operation code (e.g. "IPC", "EPA") or numeric ID.
        lang:      "EN" or "ES".

    Returns:
        JSON array of tables, each with:
          id          – numeric table ID (use in get_table_structure / get_table_data)
          name        – descriptive table name
          periodicity – data frequency (1=monthly, 3=quarterly, 12=annual…)
          last_update – ISO-style date of most recent publication
    """
    async with _client(lang) as c:
        tables = await c.get_tables(operation)

    result = []
    for t in (tables if isinstance(tables, list) else [tables]):
        per = t.get("Periodicidad") or {}
        pub = t.get("Publicacion") or {}
        result.append(
            {
                "id": t.get("Id"),
                "name": _safe_name(t.get("Nombre", "")),
                "periodicity": per.get("Nombre", per) if isinstance(per, dict) else per,
                "last_update": pub.get("PubFechaAct", pub) if isinstance(pub, dict) else pub,
                "period_start": t.get("Anyo_Ini"),
            }
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_table_structure(table_id: int, lang: str = "EN") -> str:
    """
    Return the full filter structure of a table: its groups (dimensions) and
    all available values for each group.

    Use this BEFORE calling get_table_data so you know which variable/value
    IDs to pass as filters.

    Args:
        table_id: Numeric table ID (from list_tables).
        lang:     "EN" or "ES".

    Returns:
        JSON array of groups. Each group has:
          group_id – numeric ID
          name     – dimension name (e.g. "Autonomous Communities")
          values   – list of {id, name} objects you can filter on
    """
    async with _client(lang) as c:
        groups = await c.get_table_groups(table_id)
        result = []
        for g in (groups if isinstance(groups, list) else [groups]):
            gid = g.get("Id")
            values_raw = await c.get_group_values(table_id, gid)
            values = [
                {"id": v.get("Id"), "name": _safe_name(v.get("Nombre", ""))}
                for v in (values_raw if isinstance(values_raw, list) else [values_raw])
            ]
            result.append(
                {
                    "group_id": gid,
                    "variable_id": g.get("IdVariable"),
                    "name": _safe_name(g.get("Nombre", "")),
                    "values": values,
                }
            )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools — Data retrieval
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_table_data(
    table_id: int,
    last_n: Optional[int] = 5,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    filters: Optional[list[list[str]]] = None,
    lang: str = "EN",
) -> str:
    """
    Retrieve data from a statistical table, with optional period and dimension
    filters.

    This is the primary data-retrieval tool.  Start with get_table_structure()
    to discover which filter IDs are valid.

    Args:
        table_id:   Numeric table ID (from list_tables).
        last_n:     Number of most-recent periods to return (default 5).
                    Set to null to rely on date_start/date_end instead.
        date_start: Earliest date to include, format "YYYYMMDD" (e.g. "20200101").
        date_end:   Latest date to include, format "YYYYMMDD" (e.g. "20241231").
        filters:    Optional dimension filters as a list of [variable_id, value_id]
                    pairs.  Use get_table_structure() to find valid IDs.
                    Pass ["762", ""] to include ALL values of variable 762.
                    Example: [["3", "74"], ["762", "304092"]]
        lang:       "EN" or "ES".

    Returns:
        JSON array of data rows.  Each row contains the series name, the
        period labels, and the numeric values.
    """
    filter_tuples: Optional[list[tuple[str, str]]] = None
    if filters:
        filter_tuples = [(str(f[0]), str(f[1])) for f in filters]

    async with _client(lang) as c:
        rows = await c.get_table_data(
            table_id,
            nult=last_n,
            date_start=date_start,
            date_end=date_end,
            filters=filter_tuples,
        )

    return _format_data_rows(rows)


@mcp.tool()
async def get_series_data(
    series_code: str,
    last_n: Optional[int] = 10,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    lang: str = "EN",
) -> str:
    """
    Retrieve observations for a single named time series.

    Use this when you already know the series code (e.g. "IPC251856").
    Series codes appear in the output of list_series_in_table() and in
    get_table_data() results.

    Args:
        series_code: Alphanumeric series code (e.g. "IPC251856").
        last_n:      Number of most-recent observations to return (default 10).
        date_start:  Filter from this date, format "YYYYMMDD".
        date_end:    Filter up to this date, format "YYYYMMDD".
        lang:        "EN" or "ES".

    Returns:
        JSON object with series metadata and a "data" array of {period, value}.
    """
    async with _client(lang) as c:
        raw = await c.get_series_data(
            series_code,
            nult=last_n,
            date_start=date_start,
            date_end=date_end,
        )

    # DATOS_SERIE returns either a dict with a "Data" key or a list
    if isinstance(raw, dict):
        meta = {k: v for k, v in raw.items() if k != "Data"}
        observations = raw.get("Data", [])
    else:
        meta = {}
        observations = raw if isinstance(raw, list) else []

    result = {
        "metadata": meta,
        "observations": _parse_observations(observations),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def search_operation_data(
    operation: str,
    filters: list[list[str]],
    periodicity: Optional[int] = None,
    last_n: int = 3,
    lang: str = "EN",
) -> str:
    """
    Query data across an entire operation using variable/value metadata
    filters.  This is more flexible than get_table_data because it is not
    tied to a specific pre-built table.

    Use get_operation_variables() + get_variable_values() first to discover
    valid variable/value IDs for the operation.

    Args:
        operation:   Operation code (e.g. "IPC", "EPA") or numeric ID.
        filters:     List of [variable_id, value_id] pairs.
                     Pass ["var_id", ""] to include all values of a variable.
                     Example: [["115", "29"], ["3", "84"], ["762", ""]]
        periodicity: Optional periodicity ID (1=monthly, 3=quarterly, 12=annual).
        last_n:      Number of most-recent periods to return (default 3).
        lang:        "EN" or "ES".

    Returns:
        JSON array of matching series with their recent observations.
    """
    filter_tuples = [(str(f[0]), str(f[1])) for f in filters]

    async with _client(lang) as c:
        rows = await c.get_operation_data(
            operation,
            filter_tuples,
            periodicity=periodicity,
            nult=last_n,
        )

    return _format_data_rows(rows)


# ---------------------------------------------------------------------------
# Tools — Series metadata
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_series_metadata(series_code: str, lang: str = "EN") -> str:
    """
    Return full metadata for a named series, including its defining
    variable/value pairs and publication schedule.

    Args:
        series_code: Alphanumeric series code (e.g. "IPC251856").
        lang:        "EN" or "ES".

    Returns:
        JSON object describing the series: name, operation, periodicity,
        unit, scale, classification, and the variable/value pairs that
        uniquely identify it.
    """
    async with _client(lang) as c:
        meta = await c.get_series(series_code)
        defining_values = await c.get_series_values(series_code)

    result = {
        "code": series_code,
        "name": _safe_name(meta.get("Nombre", "")),
        "operation": _safe_name((meta.get("Operacion") or {}).get("Nombre", "")),
        "periodicity": _safe_name((meta.get("Periodicidad") or {}).get("Nombre", "")),
        "unit": _safe_name((meta.get("Unidad") or {}).get("Nombre", "")),
        "scale": _safe_name((meta.get("Escala") or {}).get("Nombre", "")),
        "last_update": (meta.get("Publicacion") or {}).get("PubFechaAct"),
        "defining_values": [
            {
                "variable": _safe_name((v.get("Variable") or {}).get("Nombre", "")),
                "value": _safe_name(v.get("Nombre", "")),
            }
            for v in (defining_values if isinstance(defining_values, list) else [])
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_series_in_table(table_id: int, lang: str = "EN") -> str:
    """
    List all series that belong to a table, with their codes and defining
    variable/value labels.

    Useful for pinpointing exact series codes before calling get_series_data.
    Note: large tables can have hundreds of series.

    Args:
        table_id: Numeric table ID (from list_tables).
        lang:     "EN" or "ES".

    Returns:
        JSON array of series, each with code, name, periodicity, and
        last-update date.
    """
    async with _client(lang) as c:
        series = await c.get_series_in_table(table_id)

    result = []
    for s in (series if isinstance(series, list) else [series]):
        pub = s.get("Publicacion") or {}
        result.append(
            {
                "code": s.get("COD"),
                "name": _safe_name(s.get("Nombre", "")),
                "periodicity": _safe_name((s.get("Periodicidad") or {}).get("Nombre", "")),
                "last_update": pub.get("PubFechaAct") if isinstance(pub, dict) else pub,
                "decimals": s.get("NumDecimales"),
            }
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools — Variables & Values
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_operation_variables(operation: str, lang: str = "EN") -> str:
    """
    List all variables (filter dimensions) available for a statistical
    operation.

    Variables are dimensions such as "Geographic area", "Gender", or
    "ECOICOP product group".  Use the returned IDs in get_variable_values()
    and in the filters argument of search_operation_data().

    Args:
        operation: Operation code (e.g. "IPC") or numeric ID.
        lang:      "EN" or "ES".

    Returns:
        JSON array of variables with id and name.
    """
    async with _client(lang) as c:
        variables = await c.get_operation_variables(operation)

    result = [
        {"id": v.get("Id"), "name": _safe_name(v.get("Nombre", ""))}
        for v in (variables if isinstance(variables, list) else [variables])
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_variable_values(
    variable_id: int, operation: str, lang: str = "EN"
) -> str:
    """
    List all possible values for a specific variable within an operation.

    Args:
        variable_id: Numeric variable ID (from get_operation_variables).
        operation:   Operation code (e.g. "IPC") or numeric ID.
        lang:        "EN" or "ES".

    Returns:
        JSON array of values with id and name — use these IDs as filters.
    """
    async with _client(lang) as c:
        values = await c.get_variable_values(variable_id, operation)

    result = [
        {"id": v.get("Id"), "name": _safe_name(v.get("Nombre", ""))}
        for v in (values if isinstance(values, list) else [values])
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools — Publications
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_publications(operation: str, lang: str = "EN") -> str:
    """
    Return the publication schedule for an operation — when data is
    officially released.

    INE follows a strict annual publication calendar.  Each statistical
    operation can have multiple publications (e.g. monthly CPI, annual CPI).

    Args:
        operation: Operation code (e.g. "IPC") or numeric ID.
        lang:      "EN" or "ES".

    Returns:
        JSON array of publications with periodicity, last-update date, and
        next expected publication date.
    """
    async with _client(lang) as c:
        pubs = await c.get_publications(operation)

    result = [
        {
            "id": p.get("Id"),
            "name": _safe_name(p.get("Nombre", "")),
            "periodicity": _safe_name((p.get("Periodicidad") or {}).get("Nombre", "")),
            "last_update": p.get("PubFechaAct"),
            "next_release": p.get("PubFechaPub"),
        }
        for p in (pubs if isinstance(pubs, list) else [pubs])
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Resources — browseable reference content
# ---------------------------------------------------------------------------


@mcp.resource("ine://operations")
async def resource_operations() -> str:
    """Catalogue of all INE statistical operations (English labels)."""
    async with _client("EN") as c:
        ops = await c.get_operations()
    rows = [
        f"- **{op.get('Codigo', '?')}** (id={op.get('Id')}) — "
        f"{_safe_name(op.get('Nombre', ''))}"
        for op in (ops if isinstance(ops, list) else [ops])
    ]
    return "# INE Operations\n\n" + "\n".join(rows)


@mcp.resource("ine://operation/{code}")
async def resource_operation(code: str) -> str:
    """
    Metadata and table list for a single INE operation.

    URI: ine://operation/{code}  — replace {code} with the operation code,
    e.g. ine://operation/IPC
    """
    async with _client("EN") as c:
        op = await c.get_operation(code)
        tables = await c.get_tables(code)

    name = _safe_name(op.get("Nombre", code))
    lines = [f"# {name}\n", f"**Code:** {code}  |  **ID:** {op.get('Id')}\n"]

    lines.append("\n## Tables\n")
    for t in (tables if isinstance(tables, list) else [tables]):
        per = (t.get("Periodicidad") or {})
        freq = per.get("Nombre", "?") if isinstance(per, dict) else str(per)
        lines.append(
            f"- **id={t.get('Id')}** — {_safe_name(t.get('Nombre', ''))} "
            f"({freq})"
        )

    return "\n".join(lines)


@mcp.resource("ine://table/{table_id}/structure")
async def resource_table_structure(table_id: str) -> str:
    """
    Filter structure for a table: its groups and the available values.

    URI: ine://table/{table_id}/structure
    """
    tid = int(table_id)
    async with _client("EN") as c:
        groups = await c.get_table_groups(tid)
        lines = [f"# Table {tid} — Filter Structure\n"]
        for g in (groups if isinstance(groups, list) else [groups]):
            gid = g.get("Id")
            lines.append(f"\n## {_safe_name(g.get('Nombre', ''))} (group_id={gid}, variable_id={g.get('IdVariable')})\n")
            values_raw = await c.get_group_values(tid, gid)
            for v in (values_raw if isinstance(values_raw, list) else [values_raw]):
                lines.append(f"  - id={v.get('Id')} → {_safe_name(v.get('Nombre', ''))}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts — guided workflows
# ---------------------------------------------------------------------------


@mcp.prompt()
def explore_topic(topic: str) -> str:
    """
    Generate a step-by-step plan for finding INE data about a given topic.

    Args:
        topic: The subject you want statistics for (e.g. "inflation",
               "unemployment", "housing prices", "population").
    """
    return f"""
I want to find official Spanish statistics about **{topic}** from the INE
(Instituto Nacional de Estadística).

Please help me by:

1. Calling `list_operations()` to identify which statistical operation(s)
   are relevant to "{topic}".

2. For the most relevant operation, calling `list_tables(operation)` to
   find the most useful table.

3. Calling `get_table_structure(table_id)` to understand the available
   filter dimensions.

4. Calling `get_table_data(table_id, last_n=5)` to retrieve the latest
   5 periods of data, applying sensible filters if the table is large.

5. Presenting the results in a clear, human-readable format with proper
   labels, values, and the period/date of each observation.

Begin with step 1 now.
"""


@mcp.prompt()
def get_latest_indicator(indicator: str) -> str:
    """
    Retrieve the most recent published value for a well-known Spanish
    economic or demographic indicator.

    Args:
        indicator: Indicator name, e.g. "CPI", "unemployment rate",
                   "GDP growth", "population", "birth rate".
    """
    return f"""
Please retrieve the **most recent published value** for the Spanish
statistical indicator: **{indicator}**.

Steps:
1. Use `list_operations()` to find the relevant INE operation.
2. Use `list_tables(operation)` to find the most appropriate table
   (prefer headline/national-level tables).
3. Use `get_table_data(table_id, last_n=1)` (or last_n=2 if you need the
   previous period for comparison) to get the latest figure.
4. Report:
   - The exact indicator value with its unit
   - The reference period (month/quarter/year)
   - The publication date
   - Any notable change vs the previous period (if available)

Start now.
"""


# ---------------------------------------------------------------------------
# Internal formatters
# ---------------------------------------------------------------------------


def _parse_observations(data: list) -> list[dict]:
    """Convert raw Tempus3 Data array into clean {period, value} dicts."""
    result = []
    for point in data:
        if not isinstance(point, dict):
            result.append(point)
            continue
        period = point.get("T3_Periodo") or point.get("Periodo") or point.get("periodo")
        if isinstance(period, dict):
            period = period.get("Nombre", period)
        result.append(
            {
                "period": period,
                "year": point.get("Anyo"),
                "value": point.get("Valor"),
                "secret": point.get("Secreto"),
            }
        )
    return result


def _format_data_rows(rows: list) -> str:
    """
    Format the mixed output of DATOS_TABLA / DATOS_METADATAOPERACION.

    Each row may be a series dict with a nested "Data" list, or a flat
    observation dict depending on the tip parameter used.
    """
    if not isinstance(rows, list):
        return json.dumps(rows, ensure_ascii=False, indent=2)

    formatted = []
    for row in rows:
        if not isinstance(row, dict):
            formatted.append(row)
            continue

        data_key = next((k for k in ("Data", "data") if k in row), None)
        if data_key:
            formatted.append(
                {
                    "series_code": row.get("COD"),
                    "name": _safe_name(row.get("Nombre", "")),
                    "unit": _safe_name((row.get("Unidad") or {}).get("Nombre", "")),
                    "scale": _safe_name((row.get("Escala") or {}).get("Nombre", "")),
                    "observations": _parse_observations(row[data_key]),
                }
            )
        else:
            formatted.append(row)

    return json.dumps(formatted, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="INE MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="Transport protocol (env: MCP_TRANSPORT)",
    )
    args = parser.parse_args()

    if args.transport in ("sse", "streamable-http"):
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
