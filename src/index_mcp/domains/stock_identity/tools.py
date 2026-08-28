from __future__ import annotations

from collections.abc import Callable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from index_mcp.domains.stock_identity.models import StockResolution
from index_mcp.domains.stock_identity.service import StockIdentityService


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_stock_identity_tools(
    server: MCPServer, service_provider: Callable[[], StockIdentityService]
) -> None:
    @server.tool(
        name="resolve_a_share",
        description=(
            "识别或搜索中国 A 股个股。query 可传完整 Wind 代码（如 002311.SZ）、"
            "六位股票代码、证券简称、公司全称或名称片段。唯一匹配时 status 为 "
            "resolved；多匹配时为 ambiguous 并返回候选；无匹配时为 not_found。"
            "limit 默认 10，最大 50。"
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def resolve_a_share(query: str, limit: int = 10) -> StockResolution:
        return await service_provider().resolve_a_share(query, limit)
