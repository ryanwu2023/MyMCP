from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Protocol

from index_mcp.domains.shareholder_meeting.models import (
    ShareholderMeeting,
    ShareholderMeetingResult,
    ShareholderProposal,
)


WIND_CODE_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")


class RepositoryProtocol(Protocol):
    async def get_meetings(
        self, wind_code: str, meeting_date: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], bool]: ...


def _proposal_result(raw_is_passed: Any) -> str:
    if raw_is_passed == 1:
        return "passed"
    if raw_is_passed == 0:
        return "rejected"
    return "unknown"


class ShareholderMeetingService:
    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    async def get_shareholder_meetings(
        self, wind_code: str, meeting_date: str | None = None, limit: int = 10
    ) -> ShareholderMeetingResult:
        normalized_code = wind_code.strip().upper()
        if not WIND_CODE_PATTERN.fullmatch(normalized_code):
            raise ValueError("Wind 股票代码格式应为 000001.SZ、600000.SH 或 920000.BJ")

        normalized_date = meeting_date.strip() if meeting_date is not None else None
        if normalized_date:
            try:
                datetime.strptime(normalized_date, "%Y%m%d")
            except ValueError as exc:
                raise ValueError("meeting_date 必须是有效的 YYYYMMDD 日期") from exc
        elif meeting_date is not None:
            raise ValueError("meeting_date 必须是有效的 YYYYMMDD 日期")

        if not 1 <= limit <= 50:
            raise ValueError("limit 必须在 1 到 50 之间")

        records, truncated = await self._repository.get_meetings(
            normalized_code, normalized_date, limit
        )
        items = []
        for record in records:
            proposals = [
                ShareholderProposal(
                    proposal_num=proposal["PROPOSAL_NUM"],
                    name=proposal["PROPOSAL_NAME"],
                    voting_method=proposal["PROPOSAL_VOTING_METHOD"],
                    result=_proposal_result(proposal["IS_PASSED"]),
                    raw_is_passed=proposal["IS_PASSED"],
                )
                for proposal in record["PROPOSALS"]
            ]
            items.append(
                ShareholderMeeting(
                    meeting_object_id=str(record["MEETING_OBJECT_ID"]),
                    wind_code=record["WIND_CODE"],
                    announcement_date=record["ANNOUNCEMENT_DATE"],
                    meeting_date=record["MEETING_DATE"],
                    meeting_time=record["MEETING_TIME"],
                    meeting_name=record["MEETING_NAME"],
                    meeting_type=record["MEETING_TYPE"],
                    meeting_content=record["MEETING_CONTENT"],
                    voting_type=record["VOTING_TYPE"],
                    meeting_event_id=record["MEETING_EVENT_ID"],
                    proposals=proposals,
                )
            )

        return ShareholderMeetingResult(
            count=len(items), truncated=truncated, items=items
        )
