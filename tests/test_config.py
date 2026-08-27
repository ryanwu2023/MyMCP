from pydantic import SecretStr, ValidationError
import pytest

from index_mcp.core.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "oracle_host": "db.local",
        "oracle_service_name": "service",
        "oracle_user": "reader",
        "oracle_password": SecretStr("password"),
        "mcp_api_key": SecretStr("x" * 32),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_settings_normalize_http_and_hosts() -> None:
    settings = make_settings(
        mcp_http_path="mcp/",
        mcp_allowed_hosts="localhost:*, 10.0.0.5:* ,",
        log_level="debug",
    )

    assert settings.mcp_http_path == "/mcp"
    assert settings.allowed_hosts == ["localhost:*", "10.0.0.5:*"]
    assert settings.log_level == "DEBUG"


def test_pool_max_cannot_be_smaller_than_min() -> None:
    with pytest.raises(ValidationError, match="oracle_pool_max"):
        make_settings(oracle_pool_min=5, oracle_pool_max=2)


def test_http_requires_strong_api_key() -> None:
    settings = make_settings(mcp_api_key=SecretStr("short"))
    with pytest.raises(ValueError, match="at least 32"):
        settings.http_api_key()

