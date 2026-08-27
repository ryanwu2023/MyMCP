from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from index_mcp import __version__
from index_mcp.core.config import Settings
from index_mcp.core.database import OracleDatabase
from index_mcp.domains.index_description.repository import IndexDescriptionRepository
from index_mcp.domains.index_description.service import IndexDescriptionService
from index_mcp.domains.index_description.tools import register_index_description_tools


@dataclass
class AppRuntime:
    database: OracleDatabase | None
    index_service: IndexDescriptionService | None

    def require_index_service(self) -> IndexDescriptionService:
        if self.index_service is None:
            raise RuntimeError("指数服务尚未启动")
        return self.index_service


def create_server(
    settings: Settings,
    *,
    index_service: IndexDescriptionService | None = None,
) -> MCPServer:
    database = None if index_service is not None else OracleDatabase(settings)
    runtime = AppRuntime(database=database, index_service=index_service)

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppRuntime]:
        if runtime.database is not None:
            await runtime.database.start()
            runtime.index_service = IndexDescriptionService(
                IndexDescriptionRepository(runtime.database)
            )
        try:
            yield runtime
        finally:
            if runtime.database is not None:
                await runtime.database.close()
                runtime.index_service = None

    server = MCPServer(
        name="wind-index-mcp",
        title="WIND 股票指数基础数据",
        description="只读查询 Oracle 中的股票类指数基础信息",
        instructions=(
            "按指数代码查询时使用 get_index_by_code；按名称查找时使用 "
            "search_indices_by_name。服务不接受 SQL。"
        ),
        version=__version__,
        log_level=settings.log_level,
        lifespan=lifespan,
    )
    register_index_description_tools(server, runtime.require_index_service)

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return server

