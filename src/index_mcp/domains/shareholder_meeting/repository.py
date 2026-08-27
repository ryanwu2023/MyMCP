from __future__ import annotations

from typing import Any, Protocol

from index_mcp.domains.index_description.models import row_to_record


GET_SHAREHOLDER_MEETINGS_SQL = """
WITH selected_meetings AS (
    SELECT *
    FROM (
        SELECT
            m.OBJECT_ID AS MEETING_OBJECT_ID,
            m.S_INFO_WINDCODE AS WIND_CODE,
            m.ANN_DT AS ANNOUNCEMENT_DATE,
            m.MEETING_DT AS MEETING_DATE,
            m.MEETING_TIME,
            m.MEETING_NAME,
            m.MEETING_TYPE,
            m.MEETING_CONTENT,
            m.VOTING_TYPE,
            m.MEETEVENT_ID AS MEETING_EVENT_ID
        FROM WIND_IMP.ASHAREHOLDERSMEETING m
        WHERE m.S_INFO_WINDCODE = :wind_code
          AND (:meeting_date IS NULL OR m.MEETING_DT = :meeting_date)
          AND (m.IS_NEW = 1 OR m.IS_NEW IS NULL)
        ORDER BY m.MEETING_DT DESC NULLS LAST, m.OBJECT_ID DESC
    )
    WHERE ROWNUM <= :row_limit
)
SELECT
    m.MEETING_OBJECT_ID,
    m.WIND_CODE,
    m.ANNOUNCEMENT_DATE,
    m.MEETING_DATE,
    m.MEETING_TIME,
    m.MEETING_NAME,
    m.MEETING_TYPE,
    m.MEETING_CONTENT,
    m.VOTING_TYPE,
    m.MEETING_EVENT_ID,
    v.OBJECT_ID AS PROPOSAL_OBJECT_ID,
    v.S_EVENT_NUM AS PROPOSAL_NUM,
    v.S_EVENT_NAME AS PROPOSAL_NAME,
    v.S_INFO_TYPE AS PROPOSAL_VOTING_METHOD,
    v.IS_PASSED
FROM selected_meetings m
LEFT JOIN WIND_IMP.ASHAREINTERNETVOTING v
    ON v.S_EVENT_ID = m.MEETING_EVENT_ID
ORDER BY
    m.MEETING_DATE DESC NULLS LAST,
    m.MEETING_OBJECT_ID DESC,
    v.S_EVENT_NUM NULLS LAST
""".strip()


class DatabaseProtocol(Protocol):
    def connection(self) -> Any: ...


def _column_names(description: Any) -> list[str]:
    names: list[str] = []
    for item in description:
        name = getattr(item, "name", None)
        names.append(name if name is not None else item[0])
    return names


class ShareholderMeetingRepository:
    def __init__(self, database: DatabaseProtocol) -> None:
        self._database = database

    async def get_meetings(
        self, wind_code: str, meeting_date: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        async with self._database.connection() as connection:
            with connection.cursor() as cursor:
                await cursor.execute(
                    GET_SHAREHOLDER_MEETINGS_SQL,
                    wind_code=wind_code,
                    meeting_date=meeting_date,
                    row_limit=limit + 1,
                )
                rows = await cursor.fetchall()
                columns = _column_names(cursor.description)

        meetings: list[dict[str, Any]] = []
        meetings_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            record = row_to_record(columns, row)
            meeting_id = str(record["MEETING_OBJECT_ID"])
            meeting = meetings_by_id.get(meeting_id)
            if meeting is None:
                meeting = {
                    key: record[key]
                    for key in (
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
                    )
                }
                meeting["PROPOSALS"] = []
                meetings_by_id[meeting_id] = meeting
                meetings.append(meeting)

            if record["PROPOSAL_OBJECT_ID"] is not None:
                meeting["PROPOSALS"].append(
                    {
                        "PROPOSAL_NUM": record["PROPOSAL_NUM"],
                        "PROPOSAL_NAME": record["PROPOSAL_NAME"],
                        "PROPOSAL_VOTING_METHOD": record["PROPOSAL_VOTING_METHOD"],
                        "IS_PASSED": record["IS_PASSED"],
                    }
                )

        truncated = len(meetings) > limit
        return meetings[:limit], truncated
