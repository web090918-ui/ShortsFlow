from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import app


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

