from __future__ import annotations

import argparse
import asyncio
import os

import httpx2
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from index_mcp.core.config import PROJECT_ROOT, get_settings


async def exercise_session(session: ClientSession) -> None:
    await session.initialize()
    tools = await session.list_tools()
    exact = await session.call_tool("get_index_by_code", {"code": "000300"})
    search = await session.call_tool(
        "search_indices_by_name", {"name": "\u6caa\u6df1300", "limit": 3}
    )
    stock = await session.call_tool("resolve_a_share", {"query": "000001.SZ"})
    meetings = await session.call_tool(
        "get_shareholder_meetings", {"wind_code": "000001.SZ", "limit": 1}
    )
    exact_content = exact.structured_content or {}
    exact_data = exact_content.get("data") or {}
    search_content = search.structured_content or {}
    stock_content = stock.structured_content or {}
    meetings_content = meetings.structured_content or {}
    tool_names = [tool.name for tool in tools.tools]

    if set(tool_names) != {
        "get_index_by_code",
        "search_indices_by_name",
        "resolve_a_share",
        "get_shareholder_meetings",
    }:
        raise RuntimeError(f"Unexpected MCP tools: {tool_names}")
    if exact.is_error or not exact_content.get("found"):
        raise RuntimeError("Exact index lookup failed")
    if exact_data.get("S_INFO_CODE") != "000300":
        raise RuntimeError("Exact index lookup returned the wrong code")
    if not isinstance(exact_data.get("INDEX_INTRO"), str):
        raise RuntimeError("Oracle CLOB was not materialized as text")
    if search.is_error or not search_content.get("items"):
        raise RuntimeError("Index name search failed")
    if stock.is_error or stock_content.get("status") != "resolved":
        raise RuntimeError("A-share identity resolution failed")
    if meetings.is_error or not isinstance(meetings_content.get("items"), list):
        raise RuntimeError("Shareholder meeting lookup failed")

    print(
        {
            "tools": tool_names,
            "exact_is_error": exact.is_error,
            "exact_found": exact_content.get("found"),
            "exact_code": exact_data.get("S_INFO_CODE"),
            "exact_name": exact_data.get("S_INFO_NAME"),
            "search_is_error": search.is_error,
            "search_count": search_content.get("count"),
            "search_truncated": search_content.get("truncated"),
            "search_codes": [
                item.get("S_INFO_CODE") for item in search_content.get("items", [])
            ],
            "stock_wind_code": (stock_content.get("company") or {}).get("wind_code"),
            "shareholder_meeting_is_error": meetings.is_error,
            "shareholder_meeting_count": meetings_content.get("count"),
        }
    )


async def smoke_stdio() -> None:
    python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    parameters = StdioServerParameters(
        command=str(python),
        args=["-m", "index_mcp.run_stdio"],
        cwd=PROJECT_ROOT,
        env=dict(os.environ),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await exercise_session(session)


async def smoke_http(url: str) -> None:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.http_api_key()}"}
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await exercise_session(session)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the WIND index MCP server")
    parser.add_argument("transport", choices=["stdio", "http"])
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = parser.parse_args()
    asyncio.run(smoke_stdio() if args.transport == "stdio" else smoke_http(args.url))


if __name__ == "__main__":
    main()
