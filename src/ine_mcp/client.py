"""
Async HTTP client for the INE JSON API (Tempus3).

Base URL pattern:
    https://servicios.ine.es/wstempus/js/{LANG}/{ENDPOINT}/{ID}[?params]

Cached variant (faster for metadata, avoids repeated computation):
    https://servicios.ine.es/wstempus/jsCache/{LANG}/{ENDPOINT}/{ID}[?params]
"""

from __future__ import annotations

from typing import Any, Optional, Union
import httpx


_BASE = "https://servicios.ine.es/wstempus/js"
_CACHE = "https://servicios.ine.es/wstempus/jsCache"


class INEClient:
    """
    Thin async wrapper around the INE Tempus3 JSON API.

    Every method corresponds directly to one API endpoint so that callers
    (tools in server.py) can compose them freely without knowing URL details.
    """

    def __init__(self, lang: str = "EN") -> None:
        self.lang = lang.upper()
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, endpoint: str, *segments: str, cache: bool = True) -> str:
        base = _CACHE if cache else _BASE
        parts = [base, self.lang, endpoint, *segments]
        return "/".join(str(p) for p in parts)

    async def _get(
        self,
        endpoint: str,
        *segments: str,
        params: Optional[dict[str, Any]] = None,
        cache: bool = True,
    ) -> Any:
        url = self._url(endpoint, *segments, cache=cache)
        response = await self._http.get(url, params=params or {})
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "INEClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def get_operations(self, geo: Optional[int] = None) -> list[dict]:
        """OPERACIONES_DISPONIBLES — list all statistical operations."""
        params = {}
        if geo is not None:
            params["geo"] = geo
        return await self._get("OPERACIONES_DISPONIBLES", params=params)

    async def get_operation(self, code: str) -> dict:
        """OPERACION/{code} — details for a single operation."""
        return await self._get("OPERACION", code)

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    async def get_tables(self, operation: str) -> list[dict]:
        """TABLAS_OPERACION/{operation} — tables for an operation."""
        return await self._get("TABLAS_OPERACION", operation)

    async def get_table_groups(self, table_id: Union[str, int]) -> list[dict]:
        """GRUPOS_TABLA/{table_id} — selection groups (dimensions) of a table."""
        return await self._get("GRUPOS_TABLA", str(table_id))

    async def get_group_values(
        self,
        table_id: Union[str, int],
        group_id: Union[str, int],
        det: int = 1,
    ) -> list[dict]:
        """VALORES_GRUPOSTABLA/{table_id}/{group_id} — values for one dimension."""
        return await self._get(
            "VALORES_GRUPOSTABLA",
            str(table_id),
            str(group_id),
            params={"det": det},
        )

    # ------------------------------------------------------------------
    # Series metadata
    # ------------------------------------------------------------------

    async def get_series(self, code: str, det: int = 2) -> dict:
        """SERIE/{code} — full metadata for a single series."""
        return await self._get("SERIE", code, params={"det": det, "tip": "AM"})

    async def get_series_values(self, code: str) -> list[dict]:
        """VALORES_SERIE/{code} — the variable/value pairs that define a series."""
        return await self._get("VALORES_SERIE", code)

    async def get_series_in_table(self, table_id: Union[str, int]) -> list[dict]:
        """SERIES_TABLA/{table_id} — all series metadata for a table."""
        return await self._get("SERIES_TABLA", str(table_id), params={"tip": "AM"})

    async def get_series_in_operation(
        self, operation: str, page: int = 1
    ) -> list[dict]:
        """SERIES_OPERACION/{operation} — paginated series list (500/page)."""
        return await self._get(
            "SERIES_OPERACION", operation, params={"page": page}
        )

    # ------------------------------------------------------------------
    # Variables & Values
    # ------------------------------------------------------------------

    async def get_operation_variables(self, operation: str) -> list[dict]:
        """VARIABLES_OPERACION/{operation} — variables used in an operation."""
        return await self._get("VARIABLES_OPERACION", operation)

    async def get_variable_values(
        self, variable_id: Union[str, int], operation: str
    ) -> list[dict]:
        """VALORES_VARIABLEOPERACION/{variable_id}/{operation}."""
        return await self._get(
            "VALORES_VARIABLEOPERACION", str(variable_id), operation
        )

    # ------------------------------------------------------------------
    # Publications
    # ------------------------------------------------------------------

    async def get_publications(self, operation: str) -> list[dict]:
        """PUBLICACIONES_OPERACION/{operation} — publication calendar entries."""
        return await self._get("PUBLICACIONES_OPERACION", operation)

    # ------------------------------------------------------------------
    # Data retrieval  (these always bypass cache for freshness)
    # ------------------------------------------------------------------

    async def get_table_data(
        self,
        table_id: Union[str, int],
        *,
        nult: Optional[int] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        filters: Optional[list[tuple[str, str]]] = None,
        tip: str = "AM",
    ) -> list[dict]:
        """
        DATOS_TABLA/{table_id} — data rows for a table.

        filters: list of (variable_id, value_id) pairs passed as ?tv=var:val.
                 Pass ("var_id", "") to include all values of that variable.
        """
        params: dict[str, Any] = {"tip": tip}
        if nult is not None:
            params["nult"] = nult
        if date_start or date_end:
            params["date"] = f"{date_start or ''}:{date_end or ''}"
        if filters:
            # httpx handles repeated keys correctly when given a list
            params["tv"] = [f"{v}:{val}" for v, val in filters]
        return await self._get(
            "DATOS_TABLA", str(table_id), params=params, cache=False
        )

    async def get_series_data(
        self,
        code: str,
        *,
        nult: Optional[int] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        tip: str = "AM",
    ) -> dict:
        """DATOS_SERIE/{code} — time-series observations for one series."""
        params: dict[str, Any] = {"tip": tip}
        if nult is not None:
            params["nult"] = nult
        if date_start or date_end:
            params["date"] = f"{date_start or ''}:{date_end or ''}"
        return await self._get("DATOS_SERIE", code, params=params, cache=False)

    async def get_operation_data(
        self,
        operation: str,
        filters: list[tuple[str, str]],
        *,
        periodicity: Optional[int] = None,
        nult: int = 1,
        tip: str = "AM",
    ) -> list[dict]:
        """
        DATOS_METADATAOPERACION/{operation} — cross-section query across an
        operation using variable/value filters (g1=var:val, g2=…, …).
        """
        params: dict[str, Any] = {"nult": nult, "tip": tip}
        if periodicity is not None:
            params["p"] = periodicity
        for i, (var, val) in enumerate(filters, start=1):
            params[f"g{i}"] = f"{var}:{val}"
        return await self._get(
            "DATOS_METADATAOPERACION", operation, params=params, cache=False
        )
