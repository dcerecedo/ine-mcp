# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable)
pip install -e .

# Run the MCP server (stdio transport)
ine-mcp

# Run the MCP server (SSE transport, port 8000)
MCP_TRANSPORT=sse ine-mcp

# Build and run via Docker (SSE on port 8000)
docker build -t ine-mcp .
docker run -p 8000:8000 ine-mcp

# Run tests
pytest

# Run a single test file
pytest tests/test_foo.py
```

## Architecture

This is a two-file MCP server package (`src/ine_mcp/`):

- **`client.py`** — `INEClient`: thin async `httpx` wrapper around the INE Tempus3 REST API. Each method maps 1:1 to an API endpoint. Metadata endpoints use the cached base URL (`jsCache`); data-retrieval endpoints always bypass cache (`js`) for freshness.

- **`server.py`** — `FastMCP` server that registers all tools, resources, and prompts. Each tool creates a fresh `INEClient` via `async with _client(lang)`, calls one or more client methods, then formats and returns JSON.

### INE Data Hierarchy

```
Operations (IPC, EPA, Censo…)
  └── Tables (numeric ID)
        ├── Groups / Values  (filter dimensions + options)
        └── Series (time series, e.g. "IPC251856")
              └── Data points (observations)
```

### Two query paths

1. **Table-based** (`get_table_data`): uses `DATOS_TABLA`, filters via `tv=variable_id:value_id` query params.
2. **Operation-based** (`search_operation_data`): uses `DATOS_METADATAOPERACION`, filters via `g1=var:val`, `g2=var:val`, … params.

### Key conventions

- `lang` param (`"EN"` or `"ES"`) threads through every tool and into `INEClient`, which uppercases it and embeds it in the URL path (`/js/{LANG}/`).
- Date format for API calls: `"YYYYMMDD"` (e.g. `"20240101"`). Range passed as `date=start:end`.
- `nult=N` returns the N most-recent periods without needing exact dates.
- `tip="AM"` is the default data format parameter used in all data calls.
- Filters in tools arrive as `list[list[str]]` (JSON-safe), get converted to `list[tuple[str, str]]` before passing to the client.
