from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ShortsFlow API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"
    openai_api_key: SecretStr | None = None
    # Optional OpenAI project id (sent as the OpenAI-Project header). Needed when the
    # key is organization-scoped and the default project lacks model access.
    openai_project: str | None = None
    openai_stt_model: str = "whisper-1"
    # Task 07 Generic AI Ranking (channel-agnostic AI Score and Top 3)
    openai_ranking_model: str = "gpt-4.1-mini"
    ranking_reason_language: str = "ko"
    ranking_top_count: int = 3
    # Task 10 product Shorts: content angles use the ranking model; speech uses OpenAI TTS.
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "nova"
    product_short_max_seconds: int = 60
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
    # Task 12A Google sign-in. "disabled" keeps local development open; "google"
    # requires the OAuth client, a session secret, and a login for every creation call.
    auth_mode: Literal["disabled", "google"] = "disabled"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    session_secret: SecretStr | None = None
    session_cookie_name: str = "sf_session"
    session_ttl_seconds: int = 30 * 24 * 60 * 60
    # Public site origin and the path the frontend proxies to this API (OAuth redirect URI).
    app_public_origin: str = "http://localhost:3000"
    api_public_prefix: str = "/api"
    # Worker lease and Cloud Tasks dispatch deadline. Cloud Tasks allows at most 1800 and
    # the Cloud Run request timeout must be at least this long. Raise it together with
    # SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS when long sources must be acquired.
    processing_lease_seconds: int = 600
    # Manual-range Short pipeline (URL + start/end -> 9:16 MP4)
    shorts_acquisition_provider: Literal["auto", "apify_titan", "yt_dlp"] = "auto"
    apify_api_token: SecretStr | None = None
    apify_base_url: str = "https://api.apify.com"
    apify_titan_actor_id: str = "titan_network~titan-youtube-video-downloader"
    apify_titan_quality: str = "1080"
    apify_run_timeout_seconds: int = 480
    # Resumable media acquisition: wait this long inline, then defer the job and
    # re-check every acquisition_retry_seconds until titan_pending_max_seconds.
    titan_initial_wait_seconds: int = 90
    titan_pending_max_seconds: int = 90 * 60
    acquisition_retry_seconds: int = 60
    source_media_ttl_seconds: int = 23 * 60 * 60
    shorts_storage_backend: Literal["local", "gcs"] = "local"
    shorts_local_storage_dir: str | None = None
    gcs_bucket: str | None = None
    shorts_download_ttl_seconds: int = 24 * 60 * 60
    shorts_max_clip_seconds: int = 180
    shorts_max_source_bytes: int = 2 * 1024 * 1024 * 1024
    # Task 06 clip candidates generated from the transcript
    candidate_min_seconds: float = 15
    candidate_max_seconds: float = 60
    candidate_count_min: int = 10
    candidate_count_max: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SHORTSFLOW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
