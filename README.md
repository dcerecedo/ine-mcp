# INE MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes the full
[Spanish National Statistics Institute (INE)](https://www.ine.es) JSON API,
allowing LLM assistants to discover, explore, and retrieve official Spanish
statistical data.

## Data hierarchy

```
Operations  (statistical domains — IPC, EPA, Censo…)
  └── Tables  (pre-built cross-tabulations)
        ├── Groups / Values  (filter dimensions + their options)
        └── Series  (individual time series)
              └── Data points  (observations over time)
```

## Tools

| Tool | Description |
|------|-------------|
| `list_operations` | Discover all statistical domains |
| `get_operation` | Full metadata for one operation |
| `list_tables` | Tables for an operation |
| `get_table_structure` | Groups and filterable values for a table |
| `get_table_data` | **Main data tool** — retrieve rows with optional filters |
| `get_series_data` | Observations for a single named series |
| `search_operation_data` | Cross-operation query via metadata filters |
| `get_series_metadata` | Full metadata for a series |
| `list_series_in_table` | All series codes in a table |
| `get_operation_variables` | Variables (dimensions) for an operation |
| `get_variable_values` | Allowed values for a variable |
| `list_publications` | Publication calendar for an operation |

## Resources

| URI | Description |
|-----|-------------|
| `ine://operations` | Full catalogue of operations |
| `ine://operation/{code}` | Operation detail + table list |
| `ine://table/{id}/structure` | Table filter structure |

## Prompts

| Prompt | Description |
|--------|-------------|
| `explore_topic` | Step-by-step plan to find data on any topic |
| `get_latest_indicator` | Retrieve the latest published value for an indicator |

## Quickstart

```bash
pip install -e .
ine-mcp          # runs on stdio (default MCP transport)
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "ine": {
      "command": "ine-mcp"
    }
  }
}
```

## API reference

- [INE JSON API overview](https://www.ine.es/dyngs/DAB/en/index.htm?cid=1099)
- [INE API reference](https://www.ine.es/dyngs/DAB/index.htm?cid=1100)
