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
from index_mcp.domains.shareholder_meeting.repository import ShareholderMeetingRepository
from index_mcp.domains.shareholder_meeting.service import ShareholderMeetingService
from index_mcp.domains.shareholder_meeting.tools import register_shareholder_meeting_tools
from index_mcp.domains.stock_identity.repository import StockIdentityRepository
from index_mcp.domains.stock_identity.service import StockIdentityService
from index_mcp.domains.stock_identity.tools import register_stock_identity_tools


@dataclass
class AppRuntime:
    database: OracleDatabase | None
    index_service: IndexDescriptionService | None
    stock_identity_service: StockIdentityService | None
    shareholder_meeting_service: ShareholderMeetingService | None

    def require_index_service(self) -> IndexDescriptionService:
        if self.index_service is None:
            raise RuntimeError("指数服务尚未启动")
        return self.index_service

    def require_shareholder_meeting_service(self) -> ShareholderMeetingService:
        if self.shareholder_meeting_service is None:
            raise RuntimeError("股东大会服务尚未启动")
        return self.shareholder_meeting_service

    def require_stock_identity_service(self) -> StockIdentityService:
        if self.stock_identity_service is None:
            raise RuntimeError("A 股标的解析服务尚未启动")
        return self.stock_identity_service


def create_server(
    settings: Settings,
    *,
    index_service: IndexDescriptionService | None = None,
    stock_identity_service: StockIdentityService | None = None,
    shareholder_meeting_service: ShareholderMeetingService | None = None,
) -> MCPServer:
    injected_services = any(
        service is not None
        for service in (
            index_service,
            stock_identity_service,
            shareholder_meeting_service,
        )
    )
    database = None if injected_services else OracleDatabase(settings)
    runtime = AppRuntime(
        database=database,
        index_service=index_service,
        stock_identity_service=stock_identity_service,
        shareholder_meeting_service=shareholder_meeting_service,
    )

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppRuntime]:
        if runtime.database is not None:
            await runtime.database.start()
            runtime.index_service = IndexDescriptionService(
                IndexDescriptionRepository(runtime.database)
            )
            runtime.stock_identity_service = StockIdentityService(
                StockIdentityRepository(runtime.database)
            )
            runtime.shareholder_meeting_service = ShareholderMeetingService(
                ShareholderMeetingRepository(runtime.database),
                runtime.stock_identity_service,
            )
        try:
            yield runtime
        finally:
            if runtime.database is not None:
                await runtime.database.close()
                runtime.index_service = None
                runtime.stock_identity_service = None
                runtime.shareholder_meeting_service = None

    server = MCPServer(
        name="wind-index-mcp",
        title="WIND 市场数据查询",
        description="只读查询 Oracle 中的股票指数、A 股标的和股东大会信息",
        instructions=(
            "按指数代码查询时使用 get_index_by_code；按名称查找时使用 "
            "search_indices_by_name；识别或模糊搜索 A 股个股时使用 resolve_a_share；"
            "查询个股股东大会、议案和表决结果时使用 get_shareholder_meetings。"
            "服务不接受 SQL。"
        ),
        version=__version__,
        log_level=settings.log_level,
        lifespan=lifespan,
    )
    if runtime.database is not None or runtime.index_service is not None:
        register_index_description_tools(server, runtime.require_index_service)
    if runtime.database is not None or runtime.stock_identity_service is not None:
        register_stock_identity_tools(server, runtime.require_stock_identity_service)
    if runtime.database is not None or runtime.shareholder_meeting_service is not None:
        register_shareholder_meeting_tools(
            server, runtime.require_shareholder_meeting_service
        )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return server
