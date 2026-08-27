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
            "按完整 Wind 股票代码查询股东大会及逐项议案表决结果。wind_code 示例 "
            "000001.SZ；meeting_date 可选，格式 YYYYMMDD，不填时返回最近会议；"
            "limit 默认 10，最大 50。议案 result 为 passed、rejected 或 unknown。"
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
