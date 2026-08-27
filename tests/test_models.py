from datetime import date, datetime
from decimal import Decimal

from index_mcp.domains.index_description.models import row_to_record, to_json_value


def test_oracle_values_are_json_serializable() -> None:
    assert to_json_value(datetime(2025, 9, 15, 20, 2)) == "2025-09-15T20:02:00"
    assert to_json_value(date(2004, 12, 31)) == "2004-12-31"
    assert to_json_value(Decimal("1000")) == 1000
    assert to_json_value(Decimal("12.5")) == 12.5
    assert to_json_value(None) is None


def test_row_to_record_preserves_oracle_column_names() -> None:
    result = row_to_record(["S_INFO_CODE", "S_INFO_NAME"], ("000300", "沪深300"))
    assert result == {"S_INFO_CODE": "000300", "S_INFO_NAME": "沪深300"}

