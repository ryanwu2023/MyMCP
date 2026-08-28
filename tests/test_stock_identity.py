from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from index_mcp.domains.stock_identity.repository import (
    SEARCH_BY_FUZZY_NAME_SQL,
    StockIdentityRepository,
    escape_like_fragment,
)
from index_mcp.domains.stock_identity.service import StockIdentityService


COLUMNS = [
    "WIND_CODE",
    "STOCK_CODE",
    "SHORT_NAME",
    "FULL_NAME",
    "LIST_DATE",
    "DELIST_DATE",
    "PROVINCE",
    "CITY",
    "CHAIRMAN",
    "PRESIDENT",
    "BOARD_SECRETARY",
    "REGISTERED_CAPITAL",
    "FOUNDED_DATE",
    "COMPANY_INTRODUCTION",
    "COMPANY_TYPE",
    "WEBSITE",
    "EMAIL",
    "OFFICE_ADDRESS",
    "COUNTRY",
    "BUSINESS_SCOPE",
    "TOTAL_EMPLOYEES",
    "MAIN_BUSINESS",
]


def company_record(
    wind_code: str = "002311.SZ",
    stock_code: str = "002311",
    short_name: str = "海大集团",
    full_name: str = "广东海大集团股份有限公司",
) -> dict:
    return {
        "WIND_CODE": wind_code,
        "STOCK_CODE": stock_code,
        "SHORT_NAME": short_name,
        "FULL_NAME": full_name,
        "LIST_DATE": "20091127",
        "DELIST_DATE": None,
        "PROVINCE": "广东省",
        "CITY": "广州市",
        "CHAIRMAN": "董事长",
        "PRESIDENT": "总经理",
        "BOARD_SECRETARY": "董事会秘书",
        "REGISTERED_CAPITAL": 166374.9997,
        "FOUNDED_DATE": "20040108",
        "COMPANY_INTRODUCTION": "公司简介",
        "COMPANY_TYPE": "民营企业",
        "WEBSITE": "www.haid.com.cn",
        "EMAIL": "example@haid.com.cn",
        "OFFICE_ADDRESS": "广东省广州市",
        "COUNTRY": "中国",
        "BUSINESS_SCOPE": "经营范围",
        "TOTAL_EMPLOYEES": 10000,
        "MAIN_BUSINESS": "饲料及相关业务",
    }


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.description = [(name,) for name in COLUMNS]
        self.executed_sql = None
        self.executed_params = None
        self.fetch_size = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    async def execute(self, sql, **params) -> None:
        self.executed_sql = sql
        self.executed_params = params

    async def fetchmany(self, size: int):
        self.fetch_size = size
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


def record_row(record: dict) -> tuple:
    return tuple(record[name] for name in COLUMNS)


@pytest.mark.asyncio
async def test_repository_escapes_fuzzy_name_and_detects_truncation() -> None:
    cursor = FakeCursor(
        [
            record_row(company_record()),
            record_row(
                company_record(
                    wind_code="000001.SZ",
                    stock_code="000001",
                    short_name="海大银行",
                    full_name="海大银行股份有限公司",
                )
            ),
        ]
    )
    repository = StockIdentityRepository(FakeDatabase(cursor))

    records, truncated = await repository.search_by_fuzzy_name("海%大_\\", limit=1)

    assert records[0]["WIND_CODE"] == "002311.SZ"
    assert truncated is True
    assert cursor.executed_sql == SEARCH_BY_FUZZY_NAME_SQL
    assert cursor.executed_params == {
        "name_pattern": "%海\\%大\\_\\\\%",
        "row_limit": 2,
    }
    assert cursor.fetch_size == 2


def test_escape_like_fragment() -> None:
    assert escape_like_fragment(r"海%大_\公司") == r"海\%大\_\\公司"


class FakeRepository:
    def __init__(
        self,
        *,
        wind=None,
        stock=None,
        exact=None,
        fuzzy=None,
        truncated: bool = False,
    ) -> None:
        self.wind = wind or []
        self.stock = stock or []
        self.exact = exact or []
        self.fuzzy = fuzzy or []
        self.truncated = truncated
        self.calls: list[tuple[str, str, int]] = []

    async def find_by_wind_code(self, query: str, limit: int):
        self.calls.append(("wind", query, limit))
        return self.wind, self.truncated

    async def find_by_stock_code(self, query: str, limit: int):
        self.calls.append(("stock", query, limit))
        return self.stock, self.truncated

    async def find_by_exact_name(self, query: str, limit: int):
        self.calls.append(("exact", query, limit))
        return self.exact, self.truncated

    async def search_by_fuzzy_name(self, query: str, limit: int):
        self.calls.append(("fuzzy", query, limit))
        return self.fuzzy, self.truncated


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "repository_kwargs", "expected_call", "match_type"),
    [
        (
            " 002311.sz ",
            {"wind": [company_record()]},
            ("wind", "002311.SZ", 10),
            "wind_code",
        ),
        (
            "002311",
            {"stock": [company_record()]},
            ("stock", "002311", 10),
            "stock_code",
        ),
        (
            "海大集团",
            {"exact": [company_record()]},
            ("exact", "海大集团", 10),
            "exact_short_name",
        ),
        (
            "广东海大集团股份有限公司",
            {"exact": [company_record()]},
            ("exact", "广东海大集团股份有限公司", 10),
            "exact_full_name",
        ),
    ],
)
async def test_service_resolves_codes_and_exact_names(
    query, repository_kwargs, expected_call, match_type
) -> None:
    repository = FakeRepository(**repository_kwargs)

    result = await StockIdentityService(repository).resolve_a_share(query)

    assert repository.calls == [expected_call]
    assert result.status == "resolved"
    assert result.match_type == match_type
    assert result.company is not None
    assert result.company.wind_code == "002311.SZ"
    assert result.company.short_name == "海大集团"
    assert result.company.main_business == "饲料及相关业务"


@pytest.mark.asyncio
async def test_service_uses_fuzzy_search_only_after_exact_miss() -> None:
    repository = FakeRepository(fuzzy=[company_record()])

    result = await StockIdentityService(repository).resolve_a_share("海大")

    assert repository.calls == [
        ("exact", "海大", 10),
        ("fuzzy", "海大", 10),
    ]
    assert result.status == "resolved"
    assert result.match_type == "fuzzy_name"


@pytest.mark.asyncio
async def test_service_returns_ambiguous_candidates_without_company() -> None:
    repository = FakeRepository(
        fuzzy=[
            company_record(),
            company_record(
                wind_code="000001.SZ",
                stock_code="000001",
                short_name="海大银行",
                full_name="海大银行股份有限公司",
            ),
        ],
        truncated=True,
    )

    result = await StockIdentityService(repository).resolve_a_share("海大", limit=2)

    assert result.status == "ambiguous"
    assert result.count == 2
    assert result.candidates_truncated is True
    assert result.company is None
    assert [candidate.wind_code for candidate in result.candidates] == [
        "002311.SZ",
        "000001.SZ",
    ]


@pytest.mark.asyncio
async def test_service_returns_not_found_as_normal_result() -> None:
    result = await StockIdentityService(FakeRepository()).resolve_a_share("不存在公司")

    assert result.status == "not_found"
    assert result.match_type == "none"
    assert result.count == 0
    assert result.candidates == []
    assert result.company is None


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   "])
async def test_service_rejects_empty_query(query: str) -> None:
    with pytest.raises(ValueError, match="query 必须包含"):
        await StockIdentityService(FakeRepository()).resolve_a_share(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 51])
async def test_service_enforces_candidate_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="1 到 50"):
        await StockIdentityService(FakeRepository()).resolve_a_share("海大", limit)
