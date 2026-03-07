"""
Tests for MCP server tools and resources.

Strategy: patch INEClient methods with unittest.mock so that each tool is
tested in isolation — no real HTTP calls, no need for respx here.

Each tool test verifies:
  - The correct INEClient method(s) are called with the right arguments
  - The JSON output is correctly shaped / contains expected fields
  - The lang parameter is forwarded to the client
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import ine_mcp.server as server_module
from ine_mcp.server import (
    list_operations,
    get_operation,
    list_tables,
    get_table_structure,
    get_table_data,
    get_series_data,
    get_series_metadata,
    list_series_in_table,
    get_operation_variables,
    get_variable_values,
    list_publications,
    search_operation_data,
)


# ---------------------------------------------------------------------------
# Fixture — reusable async context-manager mock for INEClient
# ---------------------------------------------------------------------------

def make_client_mock(**method_returns):
    """
    Return a mock INEClient that behaves as an async context manager.
    Pass keyword arguments mapping method names to their return values.
    """
    mock = AsyncMock()
    for method_name, return_value in method_returns.items():
        getattr(mock, method_name).return_value = return_value

    # Make the context manager return the same mock object
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


def patch_client(**method_returns):
    """Patch ine_mcp.server._client to return a mock INEClient."""
    mock = make_client_mock(**method_returns)
    return patch.object(server_module, "_client", return_value=mock), mock


# ---------------------------------------------------------------------------
# list_operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestListOperations:
    async def test_basic_output_shape(self):
        ops_data = [
            {"Id": 1, "Codigo": "IPC", "Cod_IOE": "30138", "Nombre": "IPC"},
            {"Id": 2, "Codigo": "EPA", "Cod_IOE": "30188", "Nombre": {"Nombre": "EPA"}},
        ]
        mock = make_client_mock(get_operations=ops_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await list_operations())

        assert len(result) == 2
        assert result[0]["code"] == "IPC"
        assert result[0]["ioe_code"] == "IOE30138"
        assert result[1]["code"] == "EPA"

    async def test_geo_forwarded(self):
        mock = make_client_mock(get_operations=[])
        with patch.object(server_module, "_client", return_value=mock):
            await list_operations(geo=1)

        mock.get_operations.assert_called_once_with(geo=1)

    async def test_lang_forwarded(self):
        mock = make_client_mock(get_operations=[])
        with patch.object(server_module, "_client", return_value=mock) as p:
            await list_operations(lang="ES")

        p.assert_called_with("ES")

    async def test_single_dict_wrapped_in_list(self):
        # API sometimes returns a single dict instead of a list
        ops_data = {"Id": 1, "Codigo": "IPC", "Cod_IOE": "30138", "Nombre": "IPC"}
        mock = make_client_mock(get_operations=ops_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await list_operations())

        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_operation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOperation:
    async def test_returns_raw_json(self):
        op_data = {"Id": 1, "Codigo": "IPC", "Nombre": "IPC"}
        mock = make_client_mock(get_operation=op_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_operation("IPC"))

        assert result == op_data
        mock.get_operation.assert_called_once_with("IPC")


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestListTables:
    async def test_output_shape(self):
        tables_data = [
            {
                "Id": 50913,
                "Nombre": "IPC General",
                "Periodicidad": {"Nombre": "Mensual"},
                "Publicacion": {"PubFechaAct": "20240101"},
                "Anyo_Ini": 2002,
            }
        ]
        mock = make_client_mock(get_tables=tables_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await list_tables("IPC"))

        assert result[0]["id"] == 50913
        assert result[0]["name"] == "IPC General"
        assert result[0]["periodicity"] == "Mensual"
        assert result[0]["last_update"] == "20240101"
        assert result[0]["period_start"] == 2002

    async def test_operation_forwarded(self):
        mock = make_client_mock(get_tables=[])
        with patch.object(server_module, "_client", return_value=mock):
            await list_tables("EPA")

        mock.get_tables.assert_called_once_with("EPA")


# ---------------------------------------------------------------------------
# get_table_structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetTableStructure:
    async def test_groups_and_values(self):
        groups_data = [{"Id": 110, "IdVariable": 762, "Nombre": "Provincias"}]
        values_data = [{"Id": 1, "Nombre": "Madrid"}, {"Id": 2, "Nombre": "Barcelona"}]

        mock = make_client_mock(get_table_groups=groups_data, get_group_values=values_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_table_structure(50913))

        assert len(result) == 1
        group = result[0]
        assert group["group_id"] == 110
        assert group["variable_id"] == 762
        assert group["name"] == "Provincias"
        assert len(group["values"]) == 2
        assert group["values"][0] == {"id": 1, "name": "Madrid"}

    async def test_get_group_values_called_per_group(self):
        groups_data = [
            {"Id": 110, "IdVariable": 762, "Nombre": "Provincias"},
            {"Id": 111, "IdVariable": 3, "Nombre": "Sexo"},
        ]
        mock = make_client_mock(get_table_groups=groups_data, get_group_values=[])
        with patch.object(server_module, "_client", return_value=mock):
            await get_table_structure(50913)

        assert mock.get_group_values.call_count == 2


# ---------------------------------------------------------------------------
# get_table_data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetTableData:
    async def test_filters_converted_to_tuples(self):
        mock = make_client_mock(get_table_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await get_table_data(50913, filters=[["762", "304092"], ["3", "74"]])

        call_kwargs = mock.get_table_data.call_args
        assert call_kwargs.kwargs["filters"] == [("762", "304092"), ("3", "74")]

    async def test_last_n_forwarded_as_nult(self):
        mock = make_client_mock(get_table_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await get_table_data(50913, last_n=3)

        mock.get_table_data.assert_called_once()
        assert mock.get_table_data.call_args.kwargs["nult"] == 3

    async def test_date_range_forwarded(self):
        mock = make_client_mock(get_table_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await get_table_data(50913, date_start="20230101", date_end="20231231")

        kwargs = mock.get_table_data.call_args.kwargs
        assert kwargs["date_start"] == "20230101"
        assert kwargs["date_end"] == "20231231"

    async def test_no_filters_passes_none(self):
        mock = make_client_mock(get_table_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await get_table_data(50913)

        assert mock.get_table_data.call_args.kwargs["filters"] is None

    async def test_output_formatted(self):
        rows = [
            {
                "COD": "IPC251856",
                "Nombre": "IPC General",
                "Unidad": {"Nombre": "Índice"},
                "Escala": {},
                "Data": [{"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 109.5, "Secreto": False}],
            }
        ]
        mock = make_client_mock(get_table_data=rows)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_table_data(50913))

        assert result[0]["series_code"] == "IPC251856"
        assert result[0]["observations"][0]["value"] == 109.5


# ---------------------------------------------------------------------------
# get_series_data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetSeriesData:
    async def test_dict_response_parsed(self):
        raw = {
            "COD": "IPC251856",
            "Nombre": "IPC General",
            "Data": [{"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 109.5, "Secreto": False}],
        }
        mock = make_client_mock(get_series_data=raw)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_series_data("IPC251856"))

        assert "metadata" in result
        assert "observations" in result
        assert result["observations"][0]["value"] == 109.5
        # "Data" key must not appear in metadata
        assert "Data" not in result["metadata"]

    async def test_list_response_handled(self):
        raw = [{"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 5.0, "Secreto": None}]
        mock = make_client_mock(get_series_data=raw)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_series_data("IPC251856"))

        assert result["metadata"] == {}
        assert len(result["observations"]) == 1

    async def test_params_forwarded(self):
        mock = make_client_mock(get_series_data={})
        with patch.object(server_module, "_client", return_value=mock):
            await get_series_data("IPC251856", last_n=5, date_start="20230101", date_end="20231231")

        kwargs = mock.get_series_data.call_args.kwargs
        assert kwargs["nult"] == 5
        assert kwargs["date_start"] == "20230101"
        assert kwargs["date_end"] == "20231231"


# ---------------------------------------------------------------------------
# search_operation_data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSearchOperationData:
    async def test_filters_converted(self):
        mock = make_client_mock(get_operation_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await search_operation_data("IPC", filters=[["762", "304092"]], last_n=2)

        kwargs = mock.get_operation_data.call_args
        assert kwargs.args[1] == [("762", "304092")]
        assert kwargs.kwargs["nult"] == 2

    async def test_periodicity_forwarded(self):
        mock = make_client_mock(get_operation_data=[])
        with patch.object(server_module, "_client", return_value=mock):
            await search_operation_data("IPC", filters=[["762", "304092"]], periodicity=1)

        assert mock.get_operation_data.call_args.kwargs["periodicity"] == 1


# ---------------------------------------------------------------------------
# get_series_metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetSeriesMetadata:
    async def test_output_shape(self):
        meta = {
            "Nombre": "IPC General",
            "Operacion": {"Nombre": "IPC"},
            "Periodicidad": {"Nombre": "Mensual"},
            "Unidad": {"Nombre": "Índice"},
            "Escala": {"Nombre": ""},
            "Publicacion": {"PubFechaAct": "20240101"},
        }
        defining = [
            {"Variable": {"Nombre": "Tipo"}, "Nombre": "General"},
        ]
        mock = make_client_mock(get_series=meta, get_series_values=defining)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_series_metadata("IPC251856"))

        assert result["code"] == "IPC251856"
        assert result["name"] == "IPC General"
        assert result["operation"] == "IPC"
        assert result["periodicity"] == "Mensual"
        assert len(result["defining_values"]) == 1
        assert result["defining_values"][0]["variable"] == "Tipo"
        assert result["defining_values"][0]["value"] == "General"


# ---------------------------------------------------------------------------
# list_series_in_table
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestListSeriesInTable:
    async def test_output_shape(self):
        series_data = [
            {
                "COD": "IPC251856",
                "Nombre": "IPC General",
                "Periodicidad": {"Nombre": "Mensual"},
                "Publicacion": {"PubFechaAct": "20240101"},
                "NumDecimales": 1,
            }
        ]
        mock = make_client_mock(get_series_in_table=series_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await list_series_in_table(50913))

        assert result[0]["code"] == "IPC251856"
        assert result[0]["periodicity"] == "Mensual"
        assert result[0]["decimals"] == 1


# ---------------------------------------------------------------------------
# get_operation_variables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOperationVariables:
    async def test_output_shape(self):
        vars_data = [{"Id": 762, "Nombre": "Geografía"}]
        mock = make_client_mock(get_operation_variables=vars_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_operation_variables("IPC"))

        assert result == [{"id": 762, "name": "Geografía"}]


# ---------------------------------------------------------------------------
# get_variable_values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetVariableValues:
    async def test_output_shape(self):
        vals_data = [{"Id": 304092, "Nombre": "Nacional"}]
        mock = make_client_mock(get_variable_values=vals_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await get_variable_values(762, "IPC"))

        assert result == [{"id": 304092, "name": "Nacional"}]
        mock.get_variable_values.assert_called_once_with(762, "IPC")


# ---------------------------------------------------------------------------
# list_publications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestListPublications:
    async def test_output_shape(self):
        pubs_data = [
            {
                "Id": 5,
                "Nombre": "IPC mensual",
                "Periodicidad": {"Nombre": "Mensual"},
                "PubFechaAct": "20240101",
                "PubFechaPub": "20240201",
            }
        ]
        mock = make_client_mock(get_publications=pubs_data)
        with patch.object(server_module, "_client", return_value=mock):
            result = json.loads(await list_publications("IPC"))

        pub = result[0]
        assert pub["id"] == 5
        assert pub["name"] == "IPC mensual"
        assert pub["periodicity"] == "Mensual"
        assert pub["last_update"] == "20240101"
        assert pub["next_release"] == "20240201"
