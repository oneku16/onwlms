"""Typed and fail-closed runtime settings."""

from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic import SecretStr
from pydantic import field_validator
from pydantic import model_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported runtime environments."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


_REPOSITORY_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Validate process configuration before serving application traffic."""

    model_config = SettingsConfigDict(
        env_file=_REPOSITORY_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    APP_ENV: AppEnvironment = AppEnvironment.LOCAL
    APP_NAME: str = "OwnSIS"
    APP_BASE_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql+asyncpg://ownsis:ownsis@localhost:5432/ownsis"
    DATABASE_MIGRATION_URL: str = (
        "postgresql+psycopg://ownsis_migration:ownsis_migration@localhost:5432/ownsis"
    )
    WORKER_DATABASE_URL: str = (
        "postgresql+asyncpg://ownsis_worker:ownsis_worker@localhost:5432/ownsis"
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"
    COOKIE_SECURE: bool = True
    SESSION_COOKIE_NAME: str = "ownsis_session"
    CSRF_COOKIE_NAME: str = "ownsis_csrf"
    SESSION_TTL_SECONDS: int = Field(default=28_800, ge=300, le=604_800)
    SESSION_ENCRYPTION_KEY: str = ""
    PII_ENCRYPTION_KEY: str = ""
    INTEGRATION_ENCRYPTION_KEY: str = ""
    DEV_AUTH_ENABLED: bool = False
    DEV_AUTH_SUBJECT: str = "dev-platform-admin"
    OPENAPI_ENABLED: bool | None = None
    OWNID_ISSUER: str = ""
    OWNID_CLIENT_ID: str = ""
    OWNID_CLIENT_SECRET: str = ""
    OWNID_REDIRECT_URI: str = "http://localhost:3000/api/v1/auth/callback"
    OWNID_POST_LOGOUT_REDIRECT_URI: str = "http://localhost:3000"
    OWNID_SCOPES: str = "openid profile email offline_access"
    OWNID_HTTP_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1, le=60)
    PLATFORM_ADMIN_BOOTSTRAP_SECRET: SecretStr = SecretStr("")
    MOODLE_REQUEST_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1, le=60)
    MCP_ENABLED: bool = False
    MCP_AUDIENCE: str = ""
    MCP_RESOURCE_URL: str = "http://localhost:8000/mcp"
    WORKER_POLL_SECONDS: float = Field(default=2.0, ge=0.1, le=60)
    WORKER_LEASE_SECONDS: int = Field(default=300, ge=30, le=3600)
    WORKER_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)

    @field_validator("DATABASE_URL")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        """Reject any application database other than asynchronous PostgreSQL."""

        if not value.startswith("postgresql+asyncpg://"):
            message = "DATABASE_URL must use postgresql+asyncpg"
            raise ValueError(message)
        return value

    @field_validator("WORKER_DATABASE_URL")
    @classmethod
    def require_worker_postgresql(cls, value: str) -> str:
        """Reject a worker store other than asynchronous PostgreSQL."""

        if not value.startswith("postgresql+asyncpg://"):
            message = "WORKER_DATABASE_URL must use postgresql+asyncpg"
            raise ValueError(message)
        return value

    @field_validator("CORS_ALLOWED_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        """Require explicit credential-safe HTTP origins and reject wildcards."""

        normalized: list[str] = []
        for candidate in value.split(","):
            origin = candidate.strip()
            if not origin:
                continue
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                message = "CORS_ALLOWED_ORIGINS must contain explicit HTTP origins"
                raise ValueError(message)
            normalized.append(origin.rstrip("/"))
        if not normalized:
            message = "CORS_ALLOWED_ORIGINS must contain at least one origin"
            raise ValueError(message)
        return ",".join(dict.fromkeys(normalized))

    @field_validator(
        "SESSION_ENCRYPTION_KEY",
        "PII_ENCRYPTION_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
    )
    @classmethod
    def validate_session_key(cls, value: str) -> str:
        """Validate a supplied Fernet key without printing its contents."""

        if not value:
            return value
        try:
            Fernet(value.encode("ascii"))
        except (TypeError, ValueError) as exc:
            message = "SESSION_ENCRYPTION_KEY must be a valid Fernet key"
            raise ValueError(message) from exc
        return value

    @field_validator("PLATFORM_ADMIN_BOOTSTRAP_SECRET")
    @classmethod
    def validate_platform_admin_bootstrap_secret(cls, value: SecretStr) -> SecretStr:
        """Require a high-entropy, whitespace-stable secret when configured."""

        secret = value.get_secret_value()
        if secret and (secret != secret.strip() or len(secret) < 32):
            message = (
                "PLATFORM_ADMIN_BOOTSTRAP_SECRET must contain at least 32 "
                "characters without surrounding whitespace"
            )
            raise ValueError(message)
        return value

    @field_validator("OWNID_POST_LOGOUT_REDIRECT_URI")
    @classmethod
    def validate_post_logout_redirect_uri(cls, value: str) -> str:
        """Require an absolute browser return URL without credentials or fragment."""

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            message = "OWNID_POST_LOGOUT_REDIRECT_URI must be an absolute HTTP URL"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def require_production_security(self) -> Settings:
        """Fail closed when production identity or cookie settings are unsafe."""

        if self.MCP_ENABLED and (not self.MCP_AUDIENCE or not self.OWNID_ISSUER):
            message = "MCP_AUDIENCE and OWNID_ISSUER are required when MCP is enabled"
            raise ValueError(message)
        if self.APP_ENV is not AppEnvironment.PRODUCTION:
            return self
        required = {
            "SESSION_ENCRYPTION_KEY": self.SESSION_ENCRYPTION_KEY,
            "PII_ENCRYPTION_KEY": self.PII_ENCRYPTION_KEY,
            "INTEGRATION_ENCRYPTION_KEY": self.INTEGRATION_ENCRYPTION_KEY,
            "OWNID_ISSUER": self.OWNID_ISSUER,
            "OWNID_CLIENT_ID": self.OWNID_CLIENT_ID,
            "OWNID_CLIENT_SECRET": self.OWNID_CLIENT_SECRET,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            message = "Missing production security settings: " + ", ".join(missing)
            raise ValueError(message)
        if self.DEV_AUTH_ENABLED:
            message = "DEV_AUTH_ENABLED must be false in production"
            raise ValueError(message)
        if not self.COOKIE_SECURE:
            message = "COOKIE_SECURE must be true in production"
            raise ValueError(message)
        if not self.APP_BASE_URL.startswith("https://"):
            message = "APP_BASE_URL must use https in production"
            raise ValueError(message)
        if not self.OWNID_POST_LOGOUT_REDIRECT_URI.startswith("https://"):
            message = "OWNID_POST_LOGOUT_REDIRECT_URI must use https in production"
            raise ValueError(message)
        if any(
            not origin.startswith("https://") for origin in self.cors_allowed_origins
        ):
            message = "CORS_ALLOWED_ORIGINS must use https in production"
            raise ValueError(message)
        return self

    @property
    def cors_allowed_origins(self) -> tuple[str, ...]:
        """Return the normalized explicit browser-origin allowlist."""

        return tuple(
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        )

    @property
    def openapi_enabled(self) -> bool:
        """Expose API documentation unless production disables it by default."""

        if self.OPENAPI_ENABLED is not None:
            return self.OPENAPI_ENABLED
        return self.APP_ENV is not AppEnvironment.PRODUCTION

    @property
    def ownid_configured(self) -> bool:
        """Return whether the mandatory OwnID relying-party values exist."""

        return bool(
            self.OWNID_ISSUER and self.OWNID_CLIENT_ID and self.OWNID_CLIENT_SECRET
        )


__all__ = ["AppEnvironment", "Settings"]
