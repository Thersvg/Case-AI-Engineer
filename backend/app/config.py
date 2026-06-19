from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vigil Summit Agent"
    database_url: str = "sqlite:///./vigil.db"
    frontend_url: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    gemini_api_key: str | None = None
    llm_model: str = "gemini-2.5-flash"
    llm_provider: str = "fake"
    enrichment_provider: str = "public_web"
    enrichment_search_enabled: bool = True
    email_provider: str = "fake"
    resend_api_key: str | None = None
    email_from: str = "Vigil Summit <noreply@example.com>"
    automation_enabled: bool = True
    automation_interval_seconds: int = 30
    demo_mode: bool = True
    default_message_interval_hours: float = 24
    data_retention_days: int = 365
    auth_enabled: bool = True
    admin_email: str = "admin@vigilsummit.com"
    admin_password: str = ""
    auth_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
