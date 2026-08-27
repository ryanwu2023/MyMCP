from __future__ import annotations

from mcp import Client
from pydantic import SecretStr
import pytest

from index_mcp.core.config import Settings
from index_mcp.domains.index_description.service import IndexDescriptionService
from index_mcp.domains.shareholder_meeting.service import ShareholderMeetingService
from index_mcp.server import create_server


class FakeRepository:
    async def get_by_code(self, code: str):
        return {"S_INFO_CODE": code, "S_INFO_NAME": "沪深300"}, False

    async def search_by_name(self, name: str, limit: int):
        return [{"S_INFO_CODE": "000300", "S_INFO_NAME": name}], False


class FakeShareholderMeetingRepository:
    async def get_meetings(self, wind_code: str, meeting_date: str | None, limit: int):
        return [
            {
                "MEETING_OBJECT_ID": "1",
                "WIND_CODE": wind_code,
                "ANNOUNCEMENT_DATE": "20260801",
                "MEETING_DATE": meeting_date or "20260820",
                "MEETING_TIME": "14:30",
                "MEETING_NAME": "2026年第一次临时股东大会",
                "MEETING_TYPE": "临时股东大会",
                "MEETING_CONTENT": "审议议案甲",
                "VOTING_TYPE": "互联网投票",
                "MEETING_EVENT_ID": "EVENT-1",
                "PROPOSALS": [
                    {
                        "PROPOSAL_NUM": "01000000",
                        "PROPOSAL_NAME": "议案甲",
                        "PROPOSAL_VOTING_METHOD": "普通投票制",
                        "IS_PASSED": 1,
                    }
                ],
            }
        ], False


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
        settings(),
        index_service=IndexDescriptionService(FakeRepository()),
        shareholder_meeting_service=ShareholderMeetingService(
            FakeShareholderMeetingRepository()
        ),
    )

    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        result = await client.call_tool("get_index_by_code", {"code": "000300"})
        meeting_result = await client.call_tool(
            "get_shareholder_meetings",
            {"wind_code": "000001.SZ", "meeting_date": "20260820"},
        )

    assert names == {
        "get_index_by_code",
        "search_indices_by_name",
        "get_shareholder_meetings",
    }
    assert result.is_error is False
    assert result.structured_content == {
        "found": True,
        "data": {"S_INFO_CODE": "000300", "S_INFO_NAME": "沪深300"},
    }
    assert meeting_result.is_error is False
    assert meeting_result.structured_content["count"] == 1
    assert meeting_result.structured_content["items"][0]["proposals"] == [
        {
            "proposal_num": "01000000",
            "name": "议案甲",
            "voting_method": "普通投票制",
            "result": "passed",
            "raw_is_passed": 1,
        }
    ]


@pytest.mark.asyncio
async def test_injecting_only_index_service_does_not_expose_unavailable_tool() -> None:
    server = create_server(
        settings(), index_service=IndexDescriptionService(FakeRepository())
    )

    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == {
        "get_index_by_code",
        "search_indices_by_name",
    }
