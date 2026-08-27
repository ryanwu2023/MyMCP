from __future__ import annotations

from typing import Any, Protocol

from index_mcp.domains.index_description.models import row_to_record


GET_BY_CODE_SQL = """
SELECT *
FROM (
    SELECT a.*
    FROM WIND_IMP.AINDEXDESCRIPTION a
    WHERE a.S_INFO_INDEXTYPE = '股票类'
      AND a.S_INFO_CODE = :code
    ORDER BY a.S_INFO_WINDCODE
)
WHERE ROWNUM <= 2
""".strip()


SEARCH_BY_NAME_SQL = """
SELECT *
FROM (
    SELECT a.*
    FROM WIND_IMP.AINDEXDESCRIPTION a
    WHERE a.S_INFO_INDEXTYPE = '股票类'
      AND a.S_INFO_NAME LIKE :name_pattern ESCAPE '\\'
    ORDER BY a.S_INFO_CODE, a.S_INFO_WINDCODE
)
WHERE ROWNUM <= :row_limit
""".strip()


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


class IndexDescriptionRepository:
    def __init__(self, database: DatabaseProtocol) -> None:
        self._database = database

    async def get_by_code(self, code: str) -> tuple[dict[str, Any] | None, bool]:
        async with self._database.connection() as connection:
            with connection.cursor() as cursor:
                await cursor.execute(GET_BY_CODE_SQL, code=code)
                rows = await cursor.fetchmany(size=2)
                if not rows:
                    return None, False
                record = row_to_record(_column_names(cursor.description), rows[0])
                return record, len(rows) > 1

    async def search_by_name(
        self, name: str, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        pattern = f"%{escape_like_fragment(name)}%"
        async with self._database.connection() as connection:
            with connection.cursor() as cursor:
                await cursor.execute(
                    SEARCH_BY_NAME_SQL,
                    name_pattern=pattern,
                    row_limit=limit + 1,
                )
                rows = await cursor.fetchmany(size=limit + 1)
                columns = _column_names(cursor.description)

        truncated = len(rows) > limit
        return [row_to_record(columns, row) for row in rows[:limit]], truncated
