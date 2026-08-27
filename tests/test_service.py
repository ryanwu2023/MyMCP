from __future__ import annotations

import pytest

from index_mcp.domains.index_description.service import IndexDescriptionService


class FakeRepository:
    def __init__(self) -> None:
        self.last_code = None
        self.last_search = None

    async def get_by_code(self, code: str):
        self.last_code = code
        if code == "000300":
            return {"S_INFO_CODE": code, "S_INFO_NAME": "沪深300"}, False
        return None, False

    async def search_by_name(self, name: str, limit: int):
        self.last_search = (name, limit)
        return [{"S_INFO_CODE": "000300", "S_INFO_NAME": "沪深300"}], False


@pytest.mark.asyncio
async def test_get_by_code_normalizes_input() -> None:
    repository = FakeRepository()
    service = IndexDescriptionService(repository)

    result = await service.get_index_by_code(" 000300 ")

    assert repository.last_code == "000300"
    assert result.found is True
    assert result.data["S_INFO_NAME"] == "沪深300"


@pytest.mark.asyncio
async def test_not_found_is_normal_result() -> None:
    result = await IndexDescriptionService(FakeRepository()).get_index_by_code("missing")
    assert result.found is False
    assert result.data is None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   "])
async def test_search_rejects_empty_name(name: str) -> None:
    with pytest.raises(ValueError, match="不能为空"):
        await IndexDescriptionService(FakeRepository()).search_indices_by_name(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_search_enforces_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="1 到 100"):
        await IndexDescriptionService(FakeRepository()).search_indices_by_name("沪深300", limit)

