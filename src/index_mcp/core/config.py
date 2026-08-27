from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Service settings loaded from environment variables and the project .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    oracle_host: str
    oracle_port: int = Field(default=1521, ge=1, le=65535)
    oracle_service_name: str
    oracle_user: str
    oracle_password: SecretStr
    oracle_pool_min: int = Field(default=1, ge=1, le=50)
    oracle_pool_max: int = Field(default=5, ge=1, le=100)
    oracle_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    oracle_call_timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)

    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = Field(default=8765, ge=1, le=65535)
    mcp_http_path: str = "/mcp"
    mcp_api_key: SecretStr | None = None
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator(
        "oracle_host",
        "oracle_service_name",
        "oracle_user",
        "mcp_http_host",
        mode="before",
    )
    @classmethod
    def strip_required_strings(cls, value: object, info: ValidationInfo) -> object:
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError(f"{info.field_name} cannot be empty")
        return value

    @field_validator("mcp_http_path")
    @classmethod
    def normalize_http_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("mcp_http_path cannot be empty")
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_pool_limits(self) -> Settings:
        if self.oracle_pool_max < self.oracle_pool_min:
            raise ValueError("oracle_pool_max must be greater than or equal to oracle_pool_min")
        return self

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.mcp_allowed_hosts.split(",") if item.strip()]

    def http_api_key(self) -> str:
        if self.mcp_api_key is None:
            raise ValueError("MCP_API_KEY is required for HTTP transport")
        value = self.mcp_api_key.get_secret_value()
        if len(value) < 32:
            raise ValueError("MCP_API_KEY must contain at least 32 characters")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

