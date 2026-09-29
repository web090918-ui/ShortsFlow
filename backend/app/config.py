from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ShortsFlow API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"
    tunelio_api_key: SecretStr | None = None
    tunelio_base_url: str = "https://tunelio.dev"
    openai_api_key: SecretStr | None = None
    openai_stt_model: str = "whisper-1"
    job_repository_backend: Literal["memory", "firestore"] = "memory"
    task_dispatcher_backend: Literal["local", "cloud_tasks"] = "local"
    worker_auth_mode: Literal["disabled", "google_oidc"] = "disabled"
    gcp_project_id: str | None = None
    gcp_location: str = "asia-northeast3"
    firestore_database: str = "(default)"
    cloud_tasks_queue: str = "shortsflow-processing"
    worker_url: str | None = None
    worker_oidc_audience: str | None = None
    worker_service_account_email: str | None = None
    processing_max_attempts: int = 3
    # Manual-range Short pipeline (URL + start/end -> 9:16 MP4)
    shorts_acquisition_provider: Literal["auto", "apify_titan", "yt_dlp"] = "auto"
    apify_api_token: SecretStr | None = None
    apify_base_url: str = "https://api.apify.com"
    apify_titan_actor_id: str = "titan_network~titan-youtube-video-downloader"
    apify_titan_quality: str = "1080"
    apify_run_timeout_seconds: int = 480
    shorts_storage_backend: Literal["local", "gcs"] = "local"
    shorts_local_storage_dir: str | None = None
    gcs_bucket: str | None = None
    shorts_download_ttl_seconds: int = 24 * 60 * 60
    shorts_max_clip_seconds: int = 180
    shorts_max_source_bytes: int = 2 * 1024 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SHORTSFLOW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
