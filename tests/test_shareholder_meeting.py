from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from index_mcp.domains.shareholder_meeting.repository import (
    GET_SHAREHOLDER_MEETINGS_SQL,
    ShareholderMeetingRepository,
)
from index_mcp.domains.shareholder_meeting.service import ShareholderMeetingService
from index_mcp.domains.stock_identity.models import (
    StockCandidate,
    StockCompany,
    StockResolution,
)


COLUMNS = [
    "MEETING_OBJECT_ID",
    "WIND_CODE",
    "ANNOUNCEMENT_DATE",
    "MEETING_DATE",
    "MEETING_TIME",
    "MEETING_NAME",
    "MEETING_TYPE",
    "MEETING_CONTENT",
    "VOTING_TYPE",
    "MEETING_EVENT_ID",
    "PROPOSAL_OBJECT_ID",
    "PROPOSAL_NUM",
    "PROPOSAL_NAME",
    "PROPOSAL_VOTING_METHOD",
    "IS_PASSED",
]


def meeting_row(
    object_id: str,
    meeting_date: str,
    proposal_num: str | None,
    proposal_name: str | None,
    is_passed: int | None,
    proposal_object_id: str | None = None,
) -> tuple:
    return (
        object_id,
        "000001.SZ",
        "20260801",
        meeting_date,
        "14:30",
        "2026年第一次临时股东大会",
        "临时股东大会",
        "审议相关议案",
        "现场投票,互联网投票",
        f"EVENT-{object_id}",
        proposal_object_id or (f"PROPOSAL-{proposal_num}" if proposal_num else None),
        proposal_num,
        proposal_name,
        "普通投票制" if proposal_name else None,
        is_passed,
    )


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.description = [(name,) for name in COLUMNS]
        self.executed_sql = None
        self.executed_params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    async def execute(self, sql, **params) -> None:
        self.executed_sql = sql
        self.executed_params = params

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDatabase:
    def __init__(self, cursor: FakeCursor) -> None:
        self._connection = FakeConnection(cursor)

    @asynccontextmanager
    async def connection(self):
        yield self._connection


@pytest.mark.asyncio
async def test_repository_binds_filters_groups_proposals_and_limits_meetings() -> None:
    cursor = FakeCursor(
        [
            meeting_row("3", "20260820", "01000000", "议案甲", 1),
            meeting_row("3", "20260820", "02000000", "议案乙", 0),
            meeting_row("2", "20260720", None, None, None),
            meeting_row("1", "20260620", "01000000", "议案丙", None),
        ]
    )
    repository = ShareholderMeetingRepository(FakeDatabase(cursor))

    meetings, truncated = await repository.get_meetings(
        "000001.SZ' OR 1=1 --", meeting_date="20260820", limit=2
    )

    assert cursor.executed_sql == GET_SHAREHOLDER_MEETINGS_SQL
    assert "000001.SZ' OR 1=1 --" not in cursor.executed_sql
    assert cursor.executed_params == {
        "wind_code": "000001.SZ' OR 1=1 --",
        "meeting_date": "20260820",
        "row_limit": 3,
    }
    assert truncated is True
    assert [item["MEETING_OBJECT_ID"] for item in meetings] == ["3", "2"]
    assert [proposal["PROPOSAL_NAME"] for proposal in meetings[0]["PROPOSALS"]] == [
        "议案甲",
        "议案乙",
    ]
    assert meetings[1]["PROPOSALS"] == []


@pytest.mark.asyncio
async def test_repository_keeps_joined_proposal_with_missing_number_and_name() -> None:
    cursor = FakeCursor(
        [
            meeting_row(
                "3",
                "20260820",
                None,
                None,
                1,
                proposal_object_id="PROPOSAL-INCOMPLETE",
            )
        ]
    )
    repository = ShareholderMeetingRepository(FakeDatabase(cursor))

    meetings, truncated = await repository.get_meetings(
        "000001.SZ", meeting_date=None, limit=10
    )

    assert truncated is False
    assert meetings[0]["PROPOSALS"] == [
        {
            "PROPOSAL_NUM": None,
            "PROPOSAL_NAME": None,
            "PROPOSAL_VOTING_METHOD": None,
            "IS_PASSED": 1,
        }
    ]


class FakeRepository:
    def __init__(self, meetings=None, truncated: bool = False) -> None:
        self.meetings = meetings or []
        self.truncated = truncated
        self.last_query = None

    async def get_meetings(self, wind_code: str, meeting_date: str | None, limit: int):
        self.last_query = (wind_code, meeting_date, limit)
        return self.meetings, self.truncated


def stock_company(wind_code: str = "000001.SZ") -> StockCompany:
    return StockCompany(
        wind_code=wind_code,
        stock_code=wind_code[:6],
        short_name="平安银行",
        full_name="平安银行股份有限公司",
        list_date="19910403",
        delist_date=None,
        province="广东省",
        city="深圳市",
        chairman=None,
        president=None,
        board_secretary=None,
        registered_capital=None,
        founded_date=None,
        company_introduction=None,
        company_type=None,
        website=None,
        email=None,
        office_address=None,
        country="中国",
        business_scope=None,
        total_employees=None,
        main_business=None,
    )


def resolved_stock(query: str = "000001.SZ") -> StockResolution:
    company = stock_company()
    return StockResolution(
        status="resolved",
        match_type="wind_code",
        query=query,
        count=1,
        candidates_truncated=False,
        candidates=[StockCandidate(**company.model_dump(include=StockCandidate.model_fields))],
        company=company,
    )


class FakeIdentityService:
    def __init__(self, resolution: StockResolution | None = None) -> None:
        self.resolution = resolution or resolved_stock()
        self.last_query = None

    async def resolve_a_share(self, query: str, limit: int = 10) -> StockResolution:
        self.last_query = (query, limit)
        return self.resolution


@pytest.mark.asyncio
async def test_service_normalizes_inputs_and_maps_proposal_results() -> None:
    repository = FakeRepository(
        meetings=[
            {
                "MEETING_OBJECT_ID": "3",
                "WIND_CODE": "000001.SZ",
                "ANNOUNCEMENT_DATE": "20260801",
                "MEETING_DATE": "20260820",
                "MEETING_TIME": "14:30",
                "MEETING_NAME": "2026年第一次临时股东大会",
                "MEETING_TYPE": "临时股东大会",
                "MEETING_CONTENT": "审议相关议案",
                "VOTING_TYPE": "现场投票,互联网投票",
                "MEETING_EVENT_ID": "EVENT-3",
                "PROPOSALS": [
                    {
                        "PROPOSAL_NUM": "01000000",
                        "PROPOSAL_NAME": "议案甲",
                        "PROPOSAL_VOTING_METHOD": "普通投票制",
                        "IS_PASSED": 1,
                    },
                    {
                        "PROPOSAL_NUM": "02000000",
                        "PROPOSAL_NAME": "议案乙",
                        "PROPOSAL_VOTING_METHOD": "普通投票制",
                        "IS_PASSED": 0,
                    },
                    {
                        "PROPOSAL_NUM": "03000000",
                        "PROPOSAL_NAME": "议案丙",
                        "PROPOSAL_VOTING_METHOD": "普通投票制",
                        "IS_PASSED": None,
                    },
                ],
            }
        ],
        truncated=True,
    )
    identity = FakeIdentityService()
    service = ShareholderMeetingService(repository, identity)

    result = await service.get_shareholder_meetings(
        " 000001.sz ", meeting_date=" 20260820 ", limit=5
    )

    assert repository.last_query == ("000001.SZ", "20260820", 5)
    assert identity.last_query == (" 000001.sz ", 10)
    assert result.company.short_name == "平安银行"
    assert result.count == 1
    assert result.truncated is True
    assert [proposal.result for proposal in result.items[0].proposals] == [
        "passed",
        "rejected",
        "unknown",
    ]
    assert [proposal.raw_is_passed for proposal in result.items[0].proposals] == [
        1,
        0,
        None,
    ]


@pytest.mark.asyncio
async def test_service_rejects_unknown_company_without_querying_meetings() -> None:
    repository = FakeRepository()
    identity = FakeIdentityService(
        StockResolution(
            status="not_found",
            match_type="none",
            query="不存在公司",
            count=0,
            candidates_truncated=False,
            candidates=[],
            company=None,
        )
    )

    with pytest.raises(ValueError, match="未找到 A 股公司"):
        await ShareholderMeetingService(
            repository, identity
        ).get_shareholder_meetings("不存在公司")

    assert repository.last_query is None


@pytest.mark.asyncio
async def test_service_rejects_ambiguous_company_with_candidates() -> None:
    repository = FakeRepository()
    first = StockCandidate(
        wind_code="002311.SZ",
        stock_code="002311",
        short_name="海大集团",
        full_name="广东海大集团股份有限公司",
        list_date="20091127",
        delist_date=None,
    )
    second = StockCandidate(
        wind_code="000001.SZ",
        stock_code="000001",
        short_name="海大银行",
        full_name="海大银行股份有限公司",
        list_date="19910403",
        delist_date=None,
    )
    identity = FakeIdentityService(
        StockResolution(
            status="ambiguous",
            match_type="fuzzy_name",
            query="海大",
            count=2,
            candidates_truncated=False,
            candidates=[first, second],
            company=None,
        )
    )

    with pytest.raises(ValueError, match="002311.SZ"):
        await ShareholderMeetingService(
            repository, identity
        ).get_shareholder_meetings("海大")

    assert repository.last_query is None


@pytest.mark.asyncio
@pytest.mark.parametrize("meeting_date", ["2026-08-20", "20260230", "20261301"])
async def test_service_rejects_invalid_meeting_dates(meeting_date: str) -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        await ShareholderMeetingService(
            FakeRepository(), FakeIdentityService()
        ).get_shareholder_meetings("000001.SZ", meeting_date=meeting_date)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 51])
async def test_service_enforces_meeting_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="1 到 50"):
        await ShareholderMeetingService(
            FakeRepository(), FakeIdentityService()
        ).get_shareholder_meetings("000001.SZ", limit=limit)


@pytest.mark.asyncio
async def test_service_returns_empty_result_when_no_meeting_exists() -> None:
    result = await ShareholderMeetingService(
        FakeRepository(), FakeIdentityService()
    ).get_shareholder_meetings("000001.SZ")

    assert result.count == 0
    assert result.truncated is False
    assert result.items == []


@pytest.mark.asyncio
async def test_service_preserves_proposal_with_missing_name() -> None:
    repository = FakeRepository(
        meetings=[
            {
                "MEETING_OBJECT_ID": "4",
                "WIND_CODE": "000001.SZ",
                "ANNOUNCEMENT_DATE": None,
                "MEETING_DATE": "20260821",
                "MEETING_TIME": None,
                "MEETING_NAME": None,
                "MEETING_TYPE": "股东大会",
                "MEETING_CONTENT": None,
                "VOTING_TYPE": None,
                "MEETING_EVENT_ID": "EVENT-4",
                "PROPOSALS": [
                    {
                        "PROPOSAL_NUM": "01000000",
                        "PROPOSAL_NAME": None,
                        "PROPOSAL_VOTING_METHOD": None,
                        "IS_PASSED": None,
                    }
                ],
            }
        ]
    )

    result = await ShareholderMeetingService(
        repository, FakeIdentityService()
    ).get_shareholder_meetings("000001.SZ")

    assert result.items[0].proposals[0].name is None
    assert result.items[0].proposals[0].result == "unknown"
