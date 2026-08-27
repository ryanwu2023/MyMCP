from __future__ import annotations

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from index_mcp.core.auth import ApiKeyMiddleware
from index_mcp.core.config import get_settings
from index_mcp.logging_config import configure_logging
from index_mcp.server import create_server


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    api_key = settings.http_api_key()

    server = create_server(settings)
    app = server.streamable_http_app(
        streamable_http_path=settings.mcp_http_path,
        json_response=True,
        stateless_http=True,
        host=settings.mcp_http_host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=[],
        ),
    )
    protected_app = ApiKeyMiddleware(app, api_key, settings.mcp_http_path)

    uvicorn.run(
        protected_app,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()

