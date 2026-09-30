"""Cache of acquired source media per YouTube video and quality.

Titan needs minutes to deliver a long video and its download links stay valid for
about a day, so one successful run is reused by every transcript fallback and
render of the same source. Entries also carry the in-flight Apify run so a
Worker can resume waiting on a later Cloud Tasks delivery instead of holding an
instance open.
"""

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

from app.config import Settings


class SourceMediaStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class SourceMediaEntry(BaseModel):
    key: str
    video_id: str
    quality: str
    status: SourceMediaStatus
    provider: str
    run_id: str | None = None
    dataset_id: str | None = None
    file_url: str | None = None
    title: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None

    def is_fresh(self, now: datetime) -> bool:
        return self.expires_at is None or self.expires_at > now


class SourceMediaRepository(Protocol):
    def get(self, key: str) -> SourceMediaEntry | None: ...

    def save(self, entry: SourceMediaEntry) -> SourceMediaEntry: ...


class InMemorySourceMediaRepository:
    def __init__(self) -> None:
        self._entries: dict[str, SourceMediaEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> SourceMediaEntry | None:
        with self._lock:
            return self._entries.get(key)

    def save(self, entry: SourceMediaEntry) -> SourceMediaEntry:
        with self._lock:
            self._entries[entry.key] = entry
        return entry


class FirestoreSourceMediaRepository:
    def __init__(self, client: Any, collection: str = "source_media") -> None:
        self._collection = client.collection(collection)

    def get(self, key: str) -> SourceMediaEntry | None:
        snapshot = self._collection.document(key).get()
        if not snapshot.exists:
            return None
        return SourceMediaEntry.model_validate(snapshot.to_dict())

    def save(self, entry: SourceMediaEntry) -> SourceMediaEntry:
        self._collection.document(entry.key).set(entry.model_dump(mode="json"))
        return entry


def source_media_repository_from_settings(settings: Settings) -> SourceMediaRepository:
    if settings.job_repository_backend == "memory":
        return InMemorySourceMediaRepository()
    from google.cloud import firestore

    if not settings.gcp_project_id:
        raise RuntimeError("SHORTSFLOW_GCP_PROJECT_ID must be configured.")
    return FirestoreSourceMediaRepository(
        firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
