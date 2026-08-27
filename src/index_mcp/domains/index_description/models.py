from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, JsonValue


class IndexLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: bool
    data: dict[str, JsonValue] | None


class IndexSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    truncated: bool
    items: list[dict[str, JsonValue]]


def to_json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return str(value)


def row_to_record(column_names: list[str], row: tuple[Any, ...]) -> dict[str, JsonValue]:
    return {name: to_json_value(value) for name, value in zip(column_names, row, strict=True)}

