from __future__ import annotations

from index_mcp.core.config import get_settings
from index_mcp.logging_config import configure_logging
from index_mcp.server import create_server


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    create_server(settings).run("stdio")


if __name__ == "__main__":
    main()

