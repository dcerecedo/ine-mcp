"""
Tests for INEClient — all HTTP calls are intercepted by respx.

Each test verifies:
  - The correct URL is built (base/cache variant, lang segment, endpoint path)
  - Query parameters are forwarded correctly
  - The JSON response is returned as-is
"""

import pytest
import respx
import httpx

from ine_mcp.client import INEClient, _BASE, _CACHE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_json(data):
    """Return a respx side-effect that replies with JSON."""
    return httpx.Response(200, json=data)


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

class TestUrlBuilding:
    def test_cache_url(self):
        c = INEClient(lang="EN")
        url = c._url("OPERACIONES_DISPONIBLES", cache=True)
        assert url == f"{_CACHE}/EN/OPERACIONES_DISPONIBLES"

    def test_non_cache_url(self):
        c = INEClient(lang="ES")
        url = c._url("DATOS_TABLA", "12345", cache=False)
        assert url == f"{_BASE}/ES/DATOS_TABLA/12345"

    def test_lang_is_uppercased(self):
        c = INEClient(lang="es")
        assert c.lang == "ES"
        url = c._url("SERIE", "IPC001")
        assert "/ES/" in url


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOperations:
    @respx.mock
    async def test_returns_list(self):
        payload = [{"Id": 1, "Codigo": "IPC", "Nombre": "IPC"}]
        respx.get(f"{_CACHE}/EN/OPERACIONES_DISPONIBLES").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_operations()

        assert result == payload

    @respx.mock
    async def test_geo_param_forwarded(self):
        payload = [{"Id": 2, "Codigo": "EPA"}]
        route = respx.get(f"{_CACHE}/EN/OPERACIONES_DISPONIBLES").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            await c.get_operations(geo=1)

        assert route.called
        assert "geo=1" in str(route.calls[0].request.url)

    @respx.mock
    async def test_no_geo_param_when_none(self):
        payload = []
        route = respx.get(f"{_CACHE}/EN/OPERACIONES_DISPONIBLES").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            await c.get_operations()

        assert "geo" not in str(route.calls[0].request.url)


@pytest.mark.asyncio
class TestGetOperation:
    @respx.mock
    async def test_single_operation(self):
        payload = {"Id": 1, "Codigo": "IPC"}
        respx.get(f"{_CACHE}/EN/OPERACION/IPC").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_operation("IPC")

        assert result == payload


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetTables:
    @respx.mock
    async def test_tables_for_operation(self):
        payload = [{"Id": 50913, "Nombre": "IPC General"}]
        respx.get(f"{_CACHE}/EN/TABLAS_OPERACION/IPC").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_tables("IPC")

        assert result == payload


@pytest.mark.asyncio
class TestGetTableGroups:
    @respx.mock
    async def test_groups(self):
        payload = [{"Id": 110, "Nombre": "Provincias"}]
        respx.get(f"{_CACHE}/EN/GRUPOS_TABLA/50913").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_table_groups(50913)

        assert result == payload


@pytest.mark.asyncio
class TestGetGroupValues:
    @respx.mock
    async def test_values_with_det_param(self):
        payload = [{"Id": 1, "Nombre": "Madrid"}]
        route = respx.get(f"{_CACHE}/EN/VALORES_GRUPOSTABLA/50913/110").mock(
            return_value=httpx.Response(200, json=payload)
        )

        async with INEClient("EN") as c:
            result = await c.get_group_values(50913, 110)

        assert result == payload
        assert "det=1" in str(route.calls[0].request.url)


# ---------------------------------------------------------------------------
# Series metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetSeries:
    @respx.mock
    async def test_series_metadata(self):
        payload = {"COD": "IPC251856", "Nombre": "IPC General"}
        route = respx.get(f"{_CACHE}/EN/SERIE/IPC251856").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_series("IPC251856")

        assert result == payload
        url_str = str(route.calls[0].request.url)
        assert "det=2" in url_str
        assert "tip=AM" in url_str


@pytest.mark.asyncio
class TestGetSeriesValues:
    @respx.mock
    async def test_series_values(self):
        payload = [{"Variable": {"Nombre": "Tipo"}, "Nombre": "General"}]
        respx.get(f"{_CACHE}/EN/VALORES_SERIE/IPC251856").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_series_values("IPC251856")

        assert result == payload


@pytest.mark.asyncio
class TestGetSeriesInTable:
    @respx.mock
    async def test_series_in_table(self):
        payload = [{"COD": "IPC251856"}]
        route = respx.get(f"{_CACHE}/EN/SERIES_TABLA/50913").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_series_in_table(50913)

        assert result == payload
        assert "tip=AM" in str(route.calls[0].request.url)


@pytest.mark.asyncio
class TestGetSeriesInOperation:
    @respx.mock
    async def test_default_page_1(self):
        payload = []
        route = respx.get(f"{_CACHE}/EN/SERIES_OPERACION/IPC").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            await c.get_series_in_operation("IPC")

        assert "page=1" in str(route.calls[0].request.url)


# ---------------------------------------------------------------------------
# Variables & Values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOperationVariables:
    @respx.mock
    async def test_variables(self):
        payload = [{"Id": 762, "Nombre": "Geografía"}]
        respx.get(f"{_CACHE}/EN/VARIABLES_OPERACION/IPC").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_operation_variables("IPC")

        assert result == payload


@pytest.mark.asyncio
class TestGetVariableValues:
    @respx.mock
    async def test_variable_values(self):
        payload = [{"Id": 304092, "Nombre": "Nacional"}]
        respx.get(f"{_CACHE}/EN/VALORES_VARIABLEOPERACION/762/IPC").mock(
            return_value=httpx.Response(200, json=payload)
        )

        async with INEClient("EN") as c:
            result = await c.get_variable_values(762, "IPC")

        assert result == payload


# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetPublications:
    @respx.mock
    async def test_publications(self):
        payload = [{"Id": 5, "Nombre": "IPC mensual"}]
        respx.get(f"{_CACHE}/EN/PUBLICACIONES_OPERACION/IPC").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_publications("IPC")

        assert result == payload


# ---------------------------------------------------------------------------
# Data retrieval — must use non-cached base URL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetTableData:
    @respx.mock
    async def test_uses_non_cache_url(self):
        payload = [{"COD": "IPC251856", "Data": []}]
        route = respx.get(f"{_BASE}/EN/DATOS_TABLA/50913").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_table_data(50913)

        assert result == payload
        # Must NOT use the cache base URL
        assert _CACHE not in str(route.calls[0].request.url)

    @respx.mock
    async def test_nult_param(self):
        route = respx.get(f"{_BASE}/EN/DATOS_TABLA/50913").mock(return_value=httpx.Response(200, json=[]))

        async with INEClient("EN") as c:
            await c.get_table_data(50913, nult=5)

        assert "nult=5" in str(route.calls[0].request.url)

    @respx.mock
    async def test_date_range(self):
        route = respx.get(f"{_BASE}/EN/DATOS_TABLA/50913").mock(return_value=httpx.Response(200, json=[]))

        async with INEClient("EN") as c:
            await c.get_table_data(50913, date_start="20230101", date_end="20231231")

        assert "date=20230101%3A20231231" in str(route.calls[0].request.url) or \
               "date=20230101:20231231" in str(route.calls[0].request.url)

    @respx.mock
    async def test_filters_as_tv_params(self):
        route = respx.get(f"{_BASE}/EN/DATOS_TABLA/50913").mock(return_value=httpx.Response(200, json=[]))

        async with INEClient("EN") as c:
            await c.get_table_data(50913, filters=[("762", "304092"), ("3", "74")])

        url_str = str(route.calls[0].request.url)
        assert "762%3A304092" in url_str or "762:304092" in url_str


@pytest.mark.asyncio
class TestGetSeriesData:
    @respx.mock
    async def test_uses_non_cache_url(self):
        payload = {"COD": "IPC251856", "Data": []}
        route = respx.get(f"{_BASE}/EN/DATOS_SERIE/IPC251856").mock(return_value=httpx.Response(200, json=payload))

        async with INEClient("EN") as c:
            result = await c.get_series_data("IPC251856", nult=10)

        assert result == payload
        assert _CACHE not in str(route.calls[0].request.url)
        assert "nult=10" in str(route.calls[0].request.url)


@pytest.mark.asyncio
class TestGetOperationData:
    @respx.mock
    async def test_filters_become_g_params(self):
        payload = []
        route = respx.get(f"{_BASE}/EN/DATOS_METADATAOPERACION/IPC").mock(
            return_value=httpx.Response(200, json=payload)
        )

        async with INEClient("EN") as c:
            await c.get_operation_data("IPC", [("762", "304092"), ("3", "74")], nult=2)

        url_str = str(route.calls[0].request.url)
        assert "g1=" in url_str
        assert "g2=" in url_str
        assert "nult=2" in url_str

    @respx.mock
    async def test_periodicity_param(self):
        route = respx.get(f"{_BASE}/EN/DATOS_METADATAOPERACION/IPC").mock(
            return_value=httpx.Response(200, json=[])
        )

        async with INEClient("EN") as c:
            await c.get_operation_data("IPC", [("762", "304092")], periodicity=1)

        assert "p=1" in str(route.calls[0].request.url)


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestHttpErrors:
    @respx.mock
    async def test_raises_on_4xx(self):
        respx.get(f"{_CACHE}/EN/OPERACION/NOPE").mock(return_value=httpx.Response(404))

        with pytest.raises(httpx.HTTPStatusError):
            async with INEClient("EN") as c:
                await c.get_operation("NOPE")

    @respx.mock
    async def test_raises_on_5xx(self):
        respx.get(f"{_CACHE}/EN/OPERACIONES_DISPONIBLES").mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            async with INEClient("EN") as c:
                await c.get_operations()
