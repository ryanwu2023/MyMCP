from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from index_mcp.domains.index_description.repository import (
    GET_BY_CODE_SQL,
    SEARCH_BY_NAME_SQL,
    IndexDescriptionRepository,
    escape_like_fragment,
)


class FakeCursor:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.description = [("S_INFO_CODE",), ("S_INFO_NAME",)]
        self.executed_sql = None
        self.executed_params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    async def execute(self, sql, **params) -> None:
        self.executed_sql = sql
        self.executed_params = params

    async def fetchmany(self, size: int):
        return self.rows[:size]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDatabase:
    def __init__(self, cursor: FakeCursor) -> None:
        self._connection = FakeConnection(cursor)

    @asynccontextmanager
    async def connection(self):
        yield self._connection


@pytest.mark.asyncio
async def test_code_query_uses_bound_parameter() -> None:
    cursor = FakeCursor([("000300", "沪深300")])
    repository = IndexDescriptionRepository(FakeDatabase(cursor))

    record, duplicate = await repository.get_by_code("000300' OR 1=1 --")

    assert record["S_INFO_NAME"] == "沪深300"
    assert duplicate is False
    assert cursor.executed_sql == GET_BY_CODE_SQL
    assert "000300' OR 1=1 --" not in cursor.executed_sql
    assert cursor.executed_params == {"code": "000300' OR 1=1 --"}


@pytest.mark.asyncio
async def test_name_query_escapes_like_wildcards_and_detects_truncation() -> None:
    cursor = FakeCursor([("1", "沪深%"), ("2", "沪深_"), ("3", "沪深300")])
    repository = IndexDescriptionRepository(FakeDatabase(cursor))

    records, truncated = await repository.search_by_name("沪深%_", limit=2)

    assert len(records) == 2
    assert truncated is True
    assert cursor.executed_sql == SEARCH_BY_NAME_SQL
    assert cursor.executed_params == {
        "name_pattern": "%沪深\\%\\_%",
        "row_limit": 3,
    }


def test_escape_like_fragment() -> None:
    assert escape_like_fragment(r"a%b_c\d") == r"a\%b\_c\\d"

