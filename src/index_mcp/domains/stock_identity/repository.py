from __future__ import annotations

from typing import Any, Protocol

from index_mcp.domains.index_description.models import row_to_record


IDENTITY_COLUMNS_SQL = """
    d.S_INFO_WINDCODE AS WIND_CODE,
    d.S_INFO_CODE AS STOCK_CODE,
    d.S_INFO_NAME AS SHORT_NAME,
    d.S_INFO_COMPNAME AS FULL_NAME,
    d.S_INFO_LISTDATE AS LIST_DATE,
    d.S_INFO_DELISTDATE AS DELIST_DATE,
    i.S_INFO_PROVINCE AS PROVINCE,
    i.S_INFO_CITY AS CITY,
    i.S_INFO_CHAIRMAN AS CHAIRMAN,
    i.S_INFO_PRESIDENT AS PRESIDENT,
    i.S_INFO_BDSECRETARY AS BOARD_SECRETARY,
    i.S_INFO_REGCAPITAL AS REGISTERED_CAPITAL,
    i.S_INFO_FOUNDDATE AS FOUNDED_DATE,
    i.S_INFO_CHINESEINTRODUCTION AS COMPANY_INTRODUCTION,
    i.S_INFO_COMPTYPE AS COMPANY_TYPE,
    i.S_INFO_WEBSITE AS WEBSITE,
    i.S_INFO_EMAIL AS EMAIL,
    i.S_INFO_OFFICE AS OFFICE_ADDRESS,
    i.S_INFO_COUNTRY AS COUNTRY,
    i.S_INFO_BUSINESSSCOPE AS BUSINESS_SCOPE,
    i.S_INFO_TOTALEMPLOYEES AS TOTAL_EMPLOYEES,
    i.S_INFO_MAIN_BUSINESS AS MAIN_BUSINESS
""".strip()


LATEST_INTRODUCTION_SQL = """
WITH latest_introduction AS (
    SELECT *
    FROM (
        SELECT
            i.*,
            ROW_NUMBER() OVER (
                PARTITION BY i.S_INFO_WINDCODE
                ORDER BY
                    i.ANN_DT DESC NULLS LAST,
                    i.OPDATE DESC NULLS LAST,
                    i.OBJECT_ID DESC
            ) AS INTRO_RN
        FROM WIND_IMP.ASHAREINTRODUCTION i
    )
    WHERE INTRO_RN = 1
)
""".strip()


def _identity_query(where_clause: str, order_by: str) -> str:
    return f"""
{LATEST_INTRODUCTION_SQL}
SELECT *
FROM (
    SELECT
        {IDENTITY_COLUMNS_SQL}
    FROM WIND_IMP.ASHAREDESCRIPTION d
    LEFT JOIN latest_introduction i
        ON i.S_INFO_WINDCODE = d.S_INFO_WINDCODE
    WHERE {where_clause}
    ORDER BY {order_by}
)
WHERE ROWNUM <= :row_limit
""".strip()


FIND_BY_WIND_CODE_SQL = _identity_query(
    "UPPER(d.S_INFO_WINDCODE) = :query",
    "d.S_INFO_WINDCODE",
)

FIND_BY_STOCK_CODE_SQL = _identity_query(
    "d.S_INFO_CODE = :query",
    "d.S_INFO_WINDCODE",
)

FIND_BY_EXACT_NAME_SQL = _identity_query(
    "(d.S_INFO_NAME = :query OR d.S_INFO_COMPNAME = :query)",
    "CASE WHEN d.S_INFO_NAME = :query THEN 0 ELSE 1 END, "
    "LEAST(LENGTH(d.S_INFO_NAME), LENGTH(d.S_INFO_COMPNAME)), "
    "d.S_INFO_WINDCODE",
)

SEARCH_BY_FUZZY_NAME_SQL = _identity_query(
    "(d.S_INFO_NAME LIKE :name_pattern ESCAPE '\\' "
    "OR d.S_INFO_COMPNAME LIKE :name_pattern ESCAPE '\\')",
    "CASE WHEN d.S_INFO_NAME LIKE :name_pattern ESCAPE '\\' THEN 0 ELSE 1 END, "
    "LEAST(LENGTH(d.S_INFO_NAME), LENGTH(d.S_INFO_COMPNAME)), "
    "d.S_INFO_WINDCODE",
)


class DatabaseProtocol(Protocol):
    def connection(self) -> Any: ...


def _column_names(description: Any) -> list[str]:
    names: list[str] = []
    for item in description:
        name = getattr(item, "name", None)
        names.append(name if name is not None else item[0])
    return names


def escape_like_fragment(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StockIdentityRepository:
    def __init__(self, database: DatabaseProtocol) -> None:
        self._database = database

    async def _fetch(
        self, sql: str, *, limit: int, **params: Any
    ) -> tuple[list[dict[str, Any]], bool]:
        row_limit = limit + 1
        async with self._database.connection() as connection:
            with connection.cursor() as cursor:
                await cursor.execute(sql, row_limit=row_limit, **params)
                rows = await cursor.fetchmany(size=row_limit)
                columns = _column_names(cursor.description)

        truncated = len(rows) > limit
        return [row_to_record(columns, row) for row in rows[:limit]], truncated

    async def find_by_wind_code(
        self, query: str, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        return await self._fetch(FIND_BY_WIND_CODE_SQL, query=query, limit=limit)

    async def find_by_stock_code(
        self, query: str, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        return await self._fetch(FIND_BY_STOCK_CODE_SQL, query=query, limit=limit)

    async def find_by_exact_name(
        self, query: str, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        return await self._fetch(FIND_BY_EXACT_NAME_SQL, query=query, limit=limit)

    async def search_by_fuzzy_name(
        self, query: str, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        pattern = f"%{escape_like_fragment(query)}%"
        return await self._fetch(
            SEARCH_BY_FUZZY_NAME_SQL,
            name_pattern=pattern,
            limit=limit,
        )
