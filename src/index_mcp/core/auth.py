from __future__ import annotations

import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class ApiKeyMiddleware:
    """Require a Bearer API key for all requests to the MCP HTTP endpoint."""

    def __init__(self, app: ASGIApp, api_key: str, mcp_path: str = "/mcp") -> None:
        self.app = app
        self.api_key = api_key
        self.mcp_path = mcp_path.rstrip("/") or "/"

    def _is_mcp_path(self, path: str) -> bool:
        normalized = path.rstrip("/") or "/"
        return normalized == self.mcp_path or normalized.startswith(f"{self.mcp_path}/")

    def _is_authorized(self, headers: Headers) -> bool:
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        return (
            bool(separator)
            and scheme.casefold() == "bearer"
            and bool(token)
            and secrets.compare_digest(token, self.api_key)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._is_mcp_path(scope.get("path", "")):
            headers = Headers(scope=scope)
            if not self._is_authorized(headers):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
