from __future__ import annotations

import re
from typing import Any, Protocol

from index_mcp.domains.stock_identity.models import (
    MatchType,
    StockCandidate,
    StockCompany,
    StockResolution,
)


WIND_CODE_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")
STOCK_CODE_PATTERN = re.compile(r"^\d{6}$")


class RepositoryProtocol(Protocol):
    async def find_by_wind_code(self, query: str, limit: int): ...

    async def find_by_stock_code(self, query: str, limit: int): ...

    async def find_by_exact_name(self, query: str, limit: int): ...

    async def search_by_fuzzy_name(self, query: str, limit: int): ...


def _candidate(record: dict[str, Any]) -> StockCandidate:
    return StockCandidate(
        wind_code=record["WIND_CODE"],
        stock_code=record["STOCK_CODE"],
        short_name=record["SHORT_NAME"],
        full_name=record["FULL_NAME"],
        list_date=record["LIST_DATE"],
        delist_date=record["DELIST_DATE"],
    )


def _company(record: dict[str, Any]) -> StockCompany:
    return StockCompany(
        **_candidate(record).model_dump(),
        province=record["PROVINCE"],
        city=record["CITY"],
        chairman=record["CHAIRMAN"],
        president=record["PRESIDENT"],
        board_secretary=record["BOARD_SECRETARY"],
        registered_capital=record["REGISTERED_CAPITAL"],
        founded_date=record["FOUNDED_DATE"],
        company_introduction=record["COMPANY_INTRODUCTION"],
        company_type=record["COMPANY_TYPE"],
        website=record["WEBSITE"],
        email=record["EMAIL"],
        office_address=record["OFFICE_ADDRESS"],
        country=record["COUNTRY"],
        business_scope=record["BUSINESS_SCOPE"],
        total_employees=record["TOTAL_EMPLOYEES"],
        main_business=record["MAIN_BUSINESS"],
    )


def _deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        unique.setdefault(str(record["WIND_CODE"]), record)
    return list(unique.values())


class StockIdentityService:
    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    async def resolve_a_share(
        self, query: str, limit: int = 10
    ) -> StockResolution:
        normalized = query.strip()
        if not normalized:
            raise ValueError("query 必须包含 Wind 代码、六位股票代码或公司名称")
        if not 1 <= limit <= 50:
            raise ValueError("limit 必须在 1 到 50 之间")

        match_type: MatchType
        if WIND_CODE_PATTERN.fullmatch(normalized.upper()):
            normalized = normalized.upper()
            match_type = "wind_code"
            records, truncated = await self._repository.find_by_wind_code(
                normalized, limit
            )
        elif STOCK_CODE_PATTERN.fullmatch(normalized):
            match_type = "stock_code"
            records, truncated = await self._repository.find_by_stock_code(
                normalized, limit
            )
        else:
            records, truncated = await self._repository.find_by_exact_name(
                normalized, limit
            )
            if records:
                match_type = (
                    "exact_short_name"
                    if any(record["SHORT_NAME"] == normalized for record in records)
                    else "exact_full_name"
                )
            else:
                match_type = "fuzzy_name"
                records, truncated = await self._repository.search_by_fuzzy_name(
                    normalized, limit
                )

        records = _deduplicate(records)
        candidates = [_candidate(record) for record in records]
        if not records:
            return StockResolution(
                status="not_found",
                match_type="none",
                query=normalized,
                count=0,
                candidates_truncated=False,
                candidates=[],
                company=None,
            )

        resolved = len(records) == 1 and not truncated
        return StockResolution(
            status="resolved" if resolved else "ambiguous",
            match_type=match_type,
            query=normalized,
            count=len(candidates),
            candidates_truncated=truncated,
            candidates=candidates,
            company=_company(records[0]) if resolved else None,
        )
