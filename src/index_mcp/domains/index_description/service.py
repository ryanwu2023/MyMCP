from __future__ import annotations

import logging
from typing import Protocol

from index_mcp.domains.index_description.models import IndexLookupResult, IndexSearchResult


logger = logging.getLogger(__name__)


class RepositoryProtocol(Protocol):
    async def get_by_code(self, code: str): ...

    async def search_by_name(self, name: str, limit: int): ...


class IndexDescriptionService:
    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    async def get_index_by_code(self, code: str) -> IndexLookupResult:
        normalized = code.strip().upper()
        if not normalized:
            raise ValueError("指数代码不能为空")

        record, duplicate = await self._repository.get_by_code(normalized)
        if duplicate:
            logger.warning("Duplicate stock index code detected")
        return IndexLookupResult(found=record is not None, data=record)

    async def search_indices_by_name(self, name: str, limit: int = 20) -> IndexSearchResult:
        normalized = name.strip()
        if not normalized:
            raise ValueError("指数名称不能为空")
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")

        records, truncated = await self._repository.search_by_name(normalized, limit)
        return IndexSearchResult(count=len(records), truncated=truncated, items=records)

