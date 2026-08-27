from __future__ import annotations

from collections.abc import Callable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from index_mcp.domains.index_description.models import IndexLookupResult, IndexSearchResult
from index_mcp.domains.index_description.service import IndexDescriptionService


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_index_description_tools(
    server: MCPServer, service_provider: Callable[[], IndexDescriptionService]
) -> None:
    @server.tool(
        name="get_index_by_code",
        description=(
            "按指数代码精确查询股票类指数基础信息。输入 S_INFO_CODE，例如 000300；"
            "找不到时 found 为 false。"
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def get_index_by_code(code: str) -> IndexLookupResult:
        return await service_provider().get_index_by_code(code)

    @server.tool(
        name="search_indices_by_name",
        description=(
            "按指数名称片段模糊搜索股票类指数基础信息。limit 默认 20，最大 100；"
            "结果按指数代码稳定排序。"
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def search_indices_by_name(name: str, limit: int = 20) -> IndexSearchResult:
        return await service_provider().search_indices_by_name(name, limit)

