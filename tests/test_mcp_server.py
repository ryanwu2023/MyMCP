from __future__ import annotations

from mcp import Client
from pydantic import SecretStr
import pytest

from index_mcp.core.config import Settings
from index_mcp.domains.index_description.service import IndexDescriptionService
from index_mcp.server import create_server


class FakeRepository:
    async def get_by_code(self, code: str):
        return {"S_INFO_CODE": code, "S_INFO_NAME": "沪深300"}, False

    async def search_by_name(self, name: str, limit: int):
        return [{"S_INFO_CODE": "000300", "S_INFO_NAME": name}], False


def settings() -> Settings:
    return Settings(
        _env_file=None,
        oracle_host="db.local",
        oracle_service_name="service",
        oracle_user="reader",
        oracle_password=SecretStr("password"),
    )


@pytest.mark.asyncio
async def test_mcp_lists_and_calls_read_only_tools() -> None:
    server = create_server(
        settings(), index_service=IndexDescriptionService(FakeRepository())
    )

    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        result = await client.call_tool("get_index_by_code", {"code": "000300"})

    assert names == {"get_index_by_code", "search_indices_by_name"}
    assert result.is_error is False
    assert result.structured_content == {
        "found": True,
        "data": {"S_INFO_CODE": "000300", "S_INFO_NAME": "沪深300"},
    }
