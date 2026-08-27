from __future__ import annotations

from typing import Any

import pytest

from index_mcp.core.auth import ApiKeyMiddleware


async def invoke(path: str, authorization: str | None = None) -> list[dict[str, Any]]:
    async def downstream(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8765),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    app = ApiKeyMiddleware(downstream, "a" * 32, "/mcp")
    await app(scope, receive, send)
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer wrong"])
async def test_mcp_path_rejects_invalid_credentials(authorization: str | None) -> None:
    sent = await invoke("/mcp", authorization)
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_mcp_path_accepts_valid_bearer_key() -> None:
    sent = await invoke("/mcp/", f"Bearer {'a' * 32}")
    assert sent[0]["status"] == 204


@pytest.mark.asyncio
async def test_health_path_does_not_require_api_key() -> None:
    sent = await invoke("/health")
    assert sent[0]["status"] == 204

