from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ShortsFlow API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SHORTSFLOW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

