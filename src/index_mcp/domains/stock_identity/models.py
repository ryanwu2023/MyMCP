from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


MatchType = Literal[
    "wind_code",
    "stock_code",
    "exact_short_name",
    "exact_full_name",
    "fuzzy_name",
    "none",
]
ResolutionStatus = Literal["resolved", "ambiguous", "not_found"]


class StockCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wind_code: str
    stock_code: str
    short_name: str
    full_name: str
    list_date: str | None
    delist_date: str | None


class StockCompany(StockCandidate):
    province: str | None
    city: str | None
    chairman: str | None
    president: str | None
    board_secretary: str | None
    registered_capital: float | None
    founded_date: str | None
    company_introduction: str | None
    company_type: str | None
    website: str | None
    email: str | None
    office_address: str | None
    country: str | None
    business_scope: str | None
    total_employees: int | None
    main_business: str | None


class StockResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResolutionStatus
    match_type: MatchType
    query: str
    count: int
    candidates_truncated: bool
    candidates: list[StockCandidate]
    company: StockCompany | None
