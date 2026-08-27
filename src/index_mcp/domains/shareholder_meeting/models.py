from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ShareholderProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_num: str | None
    name: str | None
    voting_method: str | None
    result: Literal["passed", "rejected", "unknown"]
    raw_is_passed: int | float | str | None


class ShareholderMeeting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_object_id: str
    wind_code: str
    announcement_date: str | None
    meeting_date: str
    meeting_time: str | None
    meeting_name: str | None
    meeting_type: str | None
    meeting_content: str | None
    voting_type: str | None
    meeting_event_id: str | None
    proposals: list[ShareholderProposal]


class ShareholderMeetingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    truncated: bool
    items: list[ShareholderMeeting]
