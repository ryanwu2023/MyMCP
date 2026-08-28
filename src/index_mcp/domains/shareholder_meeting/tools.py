from __future__ import annotations

from collections.abc import Callable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from index_mcp.domains.shareholder_meeting.models import ShareholderMeetingResult
from index_mcp.domains.shareholder_meeting.service import ShareholderMeetingService


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_shareholder_meeting_tools(
    server: MCPServer, service_provider: Callable[[], ShareholderMeetingService]
) -> None:
    @server.tool(
        name="get_shareholder_meetings",
        description=(
            "按 A 股 Wind 代码、六位代码、证券简称、公司全称或名称片段查询"
            "股东大会及逐项议案表决结果。wind_code 示例 002311.SZ、002311、"
            "海大集团或海大；名称匹配多个公司时会返回候选提示。meeting_date "
            "可选，格式 YYYYMMDD，不填时返回最近会议；limit 默认 10，最大 50。"
            "议案 result 为 passed、rejected 或 unknown。"
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def get_shareholder_meetings(
        wind_code: str, meeting_date: str | None = None, limit: int = 10
    ) -> ShareholderMeetingResult:
        return await service_provider().get_shareholder_meetings(
            wind_code, meeting_date, limit
        )
