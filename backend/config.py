"""
Application configuration loaded from environment variables / .env file.
All settings are validated by pydantic-settings at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    """Central settings object — read from .env or environment variables."""

    # General
    dev_mode: bool = True
    """When True: auth is disabled and a dummy admin user is injected."""

    database_url: str = "sqlite+aiosqlite:///./data/subcontrol.db"
    """SQLite connection string.  The directory must exist before startup."""

    secret_key: str = "change-me-in-production"
    """Used for signing internal tokens (not Keycloak JWTs)."""

    frontend_origin: str = ""
    """
    Production URL of the React frontend, e.g. 'https://subcontrol.example.com'.
    Used to configure CORS in production.  Ignored in DEV_MODE.
    """

    # OIDC / Keycloak
    oidc_issuer_url: str = "http://localhost:8080/realms/subcontrol"
    """Issuer URL used by the *backend* to fetch JWKS and validate tokens."""

    oidc_public_issuer_url: str = ""
    """
    Public-facing issuer URL sent to the *frontend* for the browser OIDC flow.
    Set this when Keycloak is reachable by the backend on an internal Docker
    hostname (e.g. http://keycloak:8080/…) but by the browser on a different
    address (e.g. https://sso.example.com/…).
    Defaults to OIDC_ISSUER_URL when empty.
    """

    oidc_client_id: str = "subcontrol"
    oidc_client_secret: str = ""

    # AI chat — these override the app_settings DB values when set.
    # Leave empty to configure via the Settings UI instead.
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""

    # MCP server
    subcontrol_api_url: str = "http://localhost:8000"
    subcontrol_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton — import this everywhere instead of creating new instances.
settings = Settings()
