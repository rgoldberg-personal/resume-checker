from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required
    openrouter_api_key: str

    # LLM
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # File handling
    upload_dir: str = "/tmp/uploads"
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Pipeline limits
    max_concurrent_jobs: int = 5

    # Caching
    llm_cache_enabled: bool = False
    llm_cache_ttl_seconds: int = 86400

    # Logging
    log_level: str = "INFO"

    # App
    app_version: str = "1.0.0"
    celery_default_queue: str = "default"

    @field_validator("openrouter_api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, v: str) -> str:
        if not v or v == "REPLACE_WITH_YOUR_KEY":
            raise ValueError("OPENROUTER_API_KEY must be set to a valid key")
        return v


# Singleton — import this throughout the application
settings = Settings()
