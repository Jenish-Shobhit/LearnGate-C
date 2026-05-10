from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    database_url: str
    redis_url: str
    qdrant_url: str
    temporal_host: str = "localhost:7233"
    clerk_secret_key: str = ""
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    honeycomb_api_key: str = ""
    environment: str = "local"
    log_level: str = "INFO"


settings = Settings()
