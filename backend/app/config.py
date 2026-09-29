from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "Deal Intelligence"
    environment: str = "development"
    api_prefix: str = "/api"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://deal:deal@localhost:5432/deal_intelligence"
    database_pool_size: int = 10

    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 720

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.2:3b"
    llm_api_key: str = ""
    llm_timeout_seconds: int = 180
    llm_max_tokens: int = 1600
    llm_temperature: float = 0.1

    hindsight_url: str = "http://localhost:8888"
    hindsight_api_key: str = ""
    hindsight_enabled: bool = True
    hindsight_timeout_seconds: int = 600
    hindsight_bank_prefix: str = "org"

    seed_demo_data: bool = True
    seed_demo_password: str = "demo-password-123"

    log_level: str = "INFO"
    rate_limit_per_minute: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
