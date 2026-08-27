from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import oracledb

from index_mcp.core.config import Settings


logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """Raised when Oracle cannot serve a query."""


class OracleDatabase:
    """Owns the shared async Oracle connection pool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: oracledb.AsyncConnectionPool | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return

        try:
            # Return CLOB/NCLOB/BLOB values as str/bytes while the cursor is open,
            # rather than leaking LOB locator objects past the connection scope.
            oracledb.defaults.fetch_lobs = False
            pool = oracledb.create_pool_async(
                user=self._settings.oracle_user,
                password=self._settings.oracle_password.get_secret_value(),
                host=self._settings.oracle_host,
                port=self._settings.oracle_port,
                service_name=self._settings.oracle_service_name,
                min=self._settings.oracle_pool_min,
                max=self._settings.oracle_pool_max,
                increment=1,
                getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
                wait_timeout=int(self._settings.oracle_connect_timeout_seconds * 1000),
                tcp_connect_timeout=self._settings.oracle_connect_timeout_seconds,
            )
            async with pool.acquire() as connection:
                connection.call_timeout = self._settings.oracle_call_timeout_ms
                with connection.cursor() as cursor:
                    await cursor.execute("SELECT 1 FROM DUAL")
                    await cursor.fetchone()
        except oracledb.Error as exc:
            if "pool" in locals():
                await pool.close(force=True)
            logger.error("Oracle pool startup failed (%s)", type(exc).__name__)
            raise DatabaseUnavailableError("无法连接指数数据库") from exc

        self._pool = pool
        logger.info("Oracle connection pool started")

    async def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            await pool.close(force=True)
            logger.info("Oracle connection pool closed")

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[oracledb.AsyncConnection]:
        if self._pool is None:
            raise DatabaseUnavailableError("指数数据库连接池尚未启动")

        try:
            async with self._pool.acquire() as connection:
                connection.call_timeout = self._settings.oracle_call_timeout_ms
                yield connection
        except oracledb.Error as exc:
            logger.error("Oracle operation failed (%s)", type(exc).__name__)
            raise DatabaseUnavailableError("指数数据库查询暂时不可用") from exc
