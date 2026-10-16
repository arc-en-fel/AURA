"""Application settings loaded from environment variables.

Never expose privileged keys (SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET)
in frontend code, logs, or API responses.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration. Values are loaded from environment or .env file."""

    # Supabase
    supabase_url: str = Field(
        default="https://localhost.supabase.co", description="Supabase project URL"
    )
    supabase_anon_key: str = Field(
        default="mock-anon-key", description="Supabase publishable anon key"
    )
    supabase_service_role_key: str = Field(
        default="", description="Supabase service-role key (server-side only, never expose)"
    )
    supabase_jwt_secret: str = Field(
        default="", description="Supabase JWT secret for token verification"
    )

    # AI/LLM provider
    llm_provider: str = Field(default="mock", description="LLM provider: mock, local, grok")
    grok_api_key: str = Field(default="", description="Grok API key")
    grok_base_url: str = Field(default="", description="Grok API base URL")
    local_llm_base_url: str = Field(
        default="http://localhost:11434", description="Local LLM base URL"
    )
    local_llm_model: str = Field(default="", description="Local LLM model name")

    # Application
    app_name: str = Field(default="Self-Evolving CRM", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated CORS origins",
    )

    model_config = {
        "env_file": (".env", "backend/.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached singleton settings loader."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
