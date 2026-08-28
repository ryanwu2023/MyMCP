from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from index_mcp.domains.shareholder_meeting.models import (
    ShareholderMeeting,
    ShareholderMeetingResult,
    ShareholderProposal,
)
from index_mcp.domains.stock_identity.models import StockResolution


class RepositoryProtocol(Protocol):
    async def get_meetings(
        self, wind_code: str, meeting_date: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], bool]: ...


class IdentityServiceProtocol(Protocol):
    async def resolve_a_share(
        self, query: str, limit: int = 10
    ) -> StockResolution: ...


def _proposal_result(raw_is_passed: Any) -> str:
    if raw_is_passed == 1:
        return "passed"
    if raw_is_passed == 0:
        return "rejected"
    return "unknown"


class ShareholderMeetingService:
    def __init__(
        self,
        repository: RepositoryProtocol,
        identity_service: IdentityServiceProtocol,
    ) -> None:
        self._repository = repository
        self._identity_service = identity_service

    async def get_shareholder_meetings(
        self, wind_code: str, meeting_date: str | None = None, limit: int = 10
    ) -> ShareholderMeetingResult:
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

        resolution = await self._identity_service.resolve_a_share(wind_code)
        if resolution.status == "not_found":
            raise ValueError(f"未找到 A 股公司：{resolution.query}")
        if resolution.status == "ambiguous":
            candidates = "、".join(
                f"{item.short_name}（{item.wind_code}，{item.full_name}）"
                for item in resolution.candidates
            )
            suffix = "，还有更多候选" if resolution.candidates_truncated else ""
            raise ValueError(
                f"名称“{resolution.query}”匹配多个 A 股公司：{candidates}{suffix}；"
                "请使用 Wind 代码或更完整名称"
            )

        if resolution.company is None:
            raise RuntimeError("A 股标的解析结果缺少公司资料")

        records, truncated = await self._repository.get_meetings(
            resolution.company.wind_code, normalized_date, limit
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
            company=resolution.company,
            count=len(items),
            truncated=truncated,
            items=items,
        )
