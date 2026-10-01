import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.auth as auth_module
import app.processing_jobs as jobs_module
from app.auth import GoogleOAuth, InMemoryUserRepository, SessionSigner
from app.main import app
from app.processing_jobs import InMemoryProcessingJobRepository
from app.ranking import HeuristicRanker


client = TestClient(app)


class FakeOAuth(GoogleOAuth):
    def __init__(self, claims: dict) -> None:
        super().__init__("client-id", "client-secret")
        self.claims = claims
        self.exchanged: list[tuple[str, str]] = []

    def exchange_code(self, code: str, *, redirect_uri: str) -> dict:
        self.exchanged.append((code, redirect_uri))
        return {"id_token": "fake-id-token"}

    def verify_id_token(self, id_token_value: str) -> dict:
        assert id_token_value == "fake-id-token"
        return self.claims


@pytest.fixture
def google_auth(monkeypatch):
    users = InMemoryUserRepository()
    oauth = FakeOAuth({"sub": "google-sub-1", "email": "me@example.com", "name": "Me", "picture": None})
    monkeypatch.setattr(auth_module, "users", users)
    monkeypatch.setattr(auth_module, "oauth", oauth)
    monkeypatch.setattr(auth_module, "auth_required", True)
    monkeypatch.setattr(auth_module, "signer", SessionSigner("test-secret"))
    return users, oauth


def _login(path: str = "/video") -> str:
    start = client.get(f"/auth/google/start?next={path}", follow_redirects=False)
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    callback = client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert callback.status_code == 302, callback.text
    return callback.headers["location"]


def test_session_signer_round_trip_and_expiry() -> None:
    signer = SessionSigner("secret")
    token = signer.sign({"uid": "u1"}, ttl_seconds=60)

    assert signer.verify(token) is not None and signer.verify(token)["uid"] == "u1"
    assert signer.verify(token + "x") is None
    assert SessionSigner("other").verify(token) is None
    assert signer.verify(None) is None

    expired = signer.sign({"uid": "u1"}, ttl_seconds=-1)
    time.sleep(0.01)
    assert signer.verify(expired) is None


def test_start_redirects_to_google_with_signed_state(google_auth) -> None:
    response = client.get("/auth/google/start?next=/affiliate", follow_redirects=False)

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.netloc == "accounts.google.com"
    params = parse_qs(location.query)
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["http://localhost:3000/api/auth/google/callback"]
    assert "openid" in params["scope"][0]
    assert auth_module.signer.verify(params["state"][0])["next"] == "/affiliate"


def test_callback_creates_the_user_sets_the_cookie_and_redirects(google_auth) -> None:
    users, oauth = google_auth

    destination = _login("/video")

    assert destination == "/video"
    assert oauth.exchanged[0][1] == "http://localhost:3000/api/auth/google/callback"
    assert client.cookies.get("sf_session")
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "me@example.com"
    status = client.get("/auth/status").json()
    assert status == {
        "auth_required": True,
        "login_available": True,
        "user": {"id": me.json()["id"], "email": "me@example.com", "name": "Me", "picture": None},
    }
    user = users.get_by_google_sub("google-sub-1")
    assert user is not None and user.email == "me@example.com"

    # A second login for the same Google account reuses the user record.
    _login("/")
    assert users.get_by_google_sub("google-sub-1").id == user.id

    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()


def test_callback_rejects_bad_state_and_external_next(google_auth) -> None:
    bad_state = client.get("/auth/google/callback?code=abc&state=nope", follow_redirects=False)
    assert bad_state.status_code == 400

    start = client.get("/auth/google/start?next=https://evil.example.com", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cancelled = client.get(f"/auth/google/callback?error=access_denied&state={state}", follow_redirects=False)
    assert cancelled.headers["location"] == "/?login=cancelled"
    client.cookies.clear()


def test_creation_requires_login_when_auth_mode_is_google(google_auth, monkeypatch) -> None:
    monkeypatch.setattr(jobs_module, "repository", InMemoryProcessingJobRepository())
    client.cookies.clear()

    denied = client.post("/sources", json={"url": "https://youtu.be/abc12345678"})
    assert denied.status_code == 401
    assert denied.json()["detail"] == "로그인이 필요합니다."
    assert client.post(
        "/shorts",
        json={"youtube_url": "https://youtu.be/abc12345678", "start_seconds": 0, "end_seconds": 10, "rights_confirmed": True},
    ).status_code == 401
    assert client.get("/me/jobs").status_code == 401

    _login("/")
    created = client.post("/sources", json={"url": "https://youtu.be/abc12345678"})
    assert created.status_code == 201
    assert created.json()["user_id"] is not None
    client.cookies.clear()


class StubDispatcher:
    def enqueue(self, job_id, background_tasks) -> str:
        return "task"

    def schedule_resume(self, job_id, *, delay_seconds, sequence) -> str:
        return "resume"


def test_my_jobs_lists_only_the_signed_in_users_work(google_auth, monkeypatch) -> None:
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(jobs_module, "candidate_ranker", HeuristicRanker())
    users, oauth = google_auth

    _login("/")
    mine = client.post(
        "/shorts",
        json={"youtube_url": "https://youtu.be/abc12345678", "start_seconds": 0, "end_seconds": 10, "rights_confirmed": True},
    ).json()
    analysis = client.post(
        "/processing-jobs",
        json={
            "source_id": str(uuid4()),
            "source_url": "https://youtu.be/abc12345678",
            "start_seconds": 0,
            "end_seconds": 120,
            "rights_confirmed": True,
        },
    ).json()
    client.cookies.clear()

    oauth.claims = {"sub": "google-sub-2", "email": "other@example.com", "name": "Other"}
    _login("/")
    theirs = client.post(
        "/shorts",
        json={"youtube_url": "https://youtu.be/zzz12345678", "start_seconds": 0, "end_seconds": 5, "rights_confirmed": True},
    ).json()
    other_list = client.get("/me/jobs").json()["items"]
    assert [item["short"]["id"] for item in other_list] == [theirs["id"]]
    client.cookies.clear()

    oauth.claims = {"sub": "google-sub-1", "email": "me@example.com", "name": "Me"}
    _login("/")
    items = client.get("/me/jobs").json()["items"]
    assert [item["kind"] for item in items] == ["analysis", "short"]
    assert items[0]["analysis"]["id"] == analysis["id"]
    assert items[0]["analysis"]["candidate_count"] == 0
    assert items[1]["short"]["id"] == mine["id"]
    assert items[1]["short"]["artifact_state"] == "pending"
    client.cookies.clear()
