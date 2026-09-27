from uuid import UUID, uuid4

from fastapi.testclient import TestClient

import app.sources as sources_module
from app.main import app
from app.youtube import PreparedVideoSource, VideoSourceProviderError


client = TestClient(app)


def test_create_and_get_youtube_source() -> None:
    create_response = client.post(
        "/sources",
        json={"url": "https://www.youtube.com/watch?v=source123"},
    )

    assert create_response.status_code == 201
    source = create_response.json()
    assert UUID(source["id"])
    assert source["user_id"] is None
    assert source["type"] == "YOUTUBE"
    assert source["status"] == "CREATED"
    assert source["metadata"] == {"hostname": "youtube.com"}

    get_response = client.get(f"/sources/{source['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == source


def test_create_product_source_without_remote_fetch() -> None:
    response = client.post(
        "/sources",
        json={"url": "https://shop.example.com/products/camera"},
    )

    assert response.status_code == 201
    assert response.json()["type"] == "PRODUCT"
    assert response.json()["metadata"] == {"hostname": "shop.example.com"}


def test_create_upload_source() -> None:
    response = client.post(
        "/sources/upload",
        files={"file": ("clip.mp4", b"video-bytes", "video/mp4")},
    )

    assert response.status_code == 201
    source = response.json()
    assert source["type"] == "UPLOAD"
    assert source["url"] is None
    assert source["metadata"] == {
        "filename": "clip.mp4",
        "content_type": "video/mp4",
        "size_bytes": 11,
    }


def test_rejects_non_video_youtube_url() -> None:
    response = client.post(
        "/sources",
        json={"url": "https://www.youtube.com/@shortsflow"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Enter a supported YouTube video URL."


def test_rejects_invalid_url() -> None:
    response = client.post("/sources", json={"url": "not-a-url"})

    assert response.status_code == 422


def test_returns_not_found_for_unknown_source() -> None:
    response = client.get(f"/sources/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Source not found."}


class StubYouTubeProvider:
    def prepare(self, url: str) -> PreparedVideoSource:
        assert url == "https://www.youtube.com/watch?v=source123"
        return PreparedVideoSource(
            metadata={
                "youtube": {
                    "video_id": "source123",
                    "title": "Test video",
                    "duration_seconds": 125,
                },
                "media": {"video": {"format_id": "137"}, "audio": {"format_id": "140"}},
            },
            processing_reference={
                "provider": "youtube",
                "streams": {"video": {"url": "private-video-url"}},
            },
        )


def test_prepare_youtube_source_without_exposing_processing_reference(monkeypatch) -> None:
    monkeypatch.setattr(sources_module, "youtube_provider", StubYouTubeProvider())
    created = client.post(
        "/sources", json={"url": "https://www.youtube.com/watch?v=source123"}
    ).json()

    response = client.post(f"/sources/{created['id']}/prepare")

    assert response.status_code == 200
    prepared = response.json()
    assert prepared["status"] == "READY"
    assert prepared["metadata"]["youtube"]["title"] == "Test video"
    assert "processing_reference" not in prepared
    stored = sources_module.repository.get(UUID(created["id"]))
    assert stored is not None
    assert stored.processing_reference == {
        "provider": "youtube",
        "streams": {"video": {"url": "private-video-url"}},
    }


def test_create_and_prepare_youtube_source_in_one_request(monkeypatch) -> None:
    monkeypatch.setattr(sources_module, "youtube_provider", StubYouTubeProvider())

    response = client.post(
        "/sources?prepare=true",
        json={"url": "https://www.youtube.com/watch?v=source123"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "READY"
    assert response.json()["metadata"]["youtube"]["video_id"] == "source123"


def test_rejects_preparing_a_product_source() -> None:
    created = client.post(
        "/sources", json={"url": "https://shop.example.com/products/camera"}
    ).json()

    response = client.post(f"/sources/{created['id']}/prepare")

    assert response.status_code == 409


class FailingYouTubeProvider:
    def prepare(self, url: str) -> PreparedVideoSource:
        raise VideoSourceProviderError("공개 영상을 확인해 주세요.")


def test_tracks_youtube_preparation_failure(monkeypatch) -> None:
    monkeypatch.setattr(sources_module, "youtube_provider", FailingYouTubeProvider())
    created = client.post(
        "/sources", json={"url": "https://www.youtube.com/watch?v=failed123"}
    ).json()

    response = client.post(f"/sources/{created['id']}/prepare")

    assert response.status_code == 502
    assert response.json() == {"detail": "공개 영상을 확인해 주세요."}
    failed = client.get(f"/sources/{created['id']}").json()
    assert failed["status"] == "FAILED"
    assert failed["metadata"]["processing_error"] == "공개 영상을 확인해 주세요."
