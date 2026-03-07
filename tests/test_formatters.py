"""
Tests for pure helper/formatter functions in server.py.

These functions have no I/O and no async — they are tested directly
without any mocking or async infrastructure.
"""

import json
import pytest

from ine_mcp.server import _safe_name, _trim, _parse_observations, _format_data_rows


# ---------------------------------------------------------------------------
# _safe_name
# ---------------------------------------------------------------------------

class TestSafeName:
    def test_string_passthrough(self):
        assert _safe_name("IPC General") == "IPC General"

    def test_dict_with_nombre(self):
        assert _safe_name({"Nombre": "Mensual"}) == "Mensual"

    def test_dict_with_lowercase_nombre(self):
        assert _safe_name({"nombre": "Trimestral"}) == "Trimestral"

    def test_dict_prefers_uppercase_nombre(self):
        assert _safe_name({"Nombre": "A", "nombre": "B"}) == "A"

    def test_dict_fallback_to_str(self):
        result = _safe_name({"other_key": "value"})
        assert "other_key" in result

    def test_non_string_non_dict(self):
        assert _safe_name(42) == "42"

    def test_none(self):
        assert _safe_name(None) == "None"

    def test_empty_string(self):
        assert _safe_name("") == ""


# ---------------------------------------------------------------------------
# _trim
# ---------------------------------------------------------------------------

class TestTrim:
    def test_short_string_unchanged(self):
        text = "hello"
        assert _trim(text) == text

    def test_exactly_max_len_unchanged(self):
        text = "a" * 120
        assert _trim(text) == text

    def test_long_string_truncated(self):
        text = "a" * 200
        result = _trim(text)
        assert len(result) == 120
        assert result.endswith("…")

    def test_custom_max_len(self):
        text = "a" * 20
        result = _trim(text, max_len=10)
        assert len(result) == 10
        assert result.endswith("…")


# ---------------------------------------------------------------------------
# _parse_observations
# ---------------------------------------------------------------------------

class TestParseObservations:
    def test_empty_list(self):
        assert _parse_observations([]) == []

    def test_flat_observation(self):
        obs = [{"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 3.5, "Secreto": False}]
        result = _parse_observations(obs)
        assert result == [{"period": "Enero", "year": 2024, "value": 3.5, "secret": False}]

    def test_periodo_key_fallback(self):
        obs = [{"Periodo": "Febrero", "Anyo": 2024, "Valor": 4.0, "Secreto": None}]
        result = _parse_observations(obs)
        assert result[0]["period"] == "Febrero"

    def test_lowercase_periodo_fallback(self):
        obs = [{"periodo": "Marzo", "Anyo": 2024, "Valor": 2.1, "Secreto": None}]
        result = _parse_observations(obs)
        assert result[0]["period"] == "Marzo"

    def test_period_as_dict_extracts_nombre(self):
        obs = [{"T3_Periodo": {"Nombre": "Abril"}, "Anyo": 2024, "Valor": 1.0, "Secreto": None}]
        result = _parse_observations(obs)
        assert result[0]["period"] == "Abril"

    def test_non_dict_passthrough(self):
        obs = ["raw_string", 42]
        result = _parse_observations(obs)
        assert result == ["raw_string", 42]

    def test_missing_period_is_none(self):
        obs = [{"Anyo": 2024, "Valor": 5.0, "Secreto": None}]
        result = _parse_observations(obs)
        assert result[0]["period"] is None

    def test_multiple_observations(self):
        obs = [
            {"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 1.0, "Secreto": False},
            {"T3_Periodo": "Febrero", "Anyo": 2024, "Valor": 2.0, "Secreto": False},
        ]
        result = _parse_observations(obs)
        assert len(result) == 2
        assert result[0]["value"] == 1.0
        assert result[1]["value"] == 2.0


# ---------------------------------------------------------------------------
# _format_data_rows
# ---------------------------------------------------------------------------

class TestFormatDataRows:
    def test_non_list_input(self):
        raw = {"unexpected": "dict"}
        output = json.loads(_format_data_rows(raw))
        assert output == raw

    def test_empty_list(self):
        assert json.loads(_format_data_rows([])) == []

    def test_row_with_Data_key(self):
        rows = [
            {
                "COD": "IPC251856",
                "Nombre": "IPC General",
                "Unidad": {"Nombre": "Índice"},
                "Escala": {"Nombre": ""},
                "Data": [{"T3_Periodo": "Enero", "Anyo": 2024, "Valor": 109.5, "Secreto": False}],
            }
        ]
        result = json.loads(_format_data_rows(rows))
        assert len(result) == 1
        row = result[0]
        assert row["series_code"] == "IPC251856"
        assert row["name"] == "IPC General"
        assert row["unit"] == "Índice"
        assert len(row["observations"]) == 1
        assert row["observations"][0]["value"] == 109.5

    def test_row_with_lowercase_data_key(self):
        rows = [
            {
                "COD": "EPA001",
                "Nombre": "Tasa de paro",
                "Unidad": {},
                "Escala": {},
                "data": [{"T3_Periodo": "T1", "Anyo": 2024, "Valor": 11.5, "Secreto": None}],
            }
        ]
        result = json.loads(_format_data_rows(rows))
        assert result[0]["observations"][0]["value"] == 11.5

    def test_flat_row_passthrough(self):
        rows = [{"Id": 1, "Nombre": "flat row without Data key"}]
        result = json.loads(_format_data_rows(rows))
        assert result == rows

    def test_non_dict_items_passthrough(self):
        rows = ["string_item", 42]
        result = json.loads(_format_data_rows(rows))
        assert result == rows

    def test_mixed_rows(self):
        rows = [
            {
                "COD": "IPC001",
                "Nombre": "Serie A",
                "Unidad": {},
                "Escala": {},
                "Data": [],
            },
            {"flat": "row"},
        ]
        result = json.loads(_format_data_rows(rows))
        assert result[0]["series_code"] == "IPC001"
        assert result[1] == {"flat": "row"}

    def test_output_is_valid_json(self):
        rows = [{"COD": "X", "Nombre": "España ñ", "Unidad": {}, "Escala": {}, "Data": []}]
        output = _format_data_rows(rows)
        assert isinstance(json.loads(output), list)
        # Non-ASCII characters must be preserved (ensure_ascii=False)
        assert "España" in output
