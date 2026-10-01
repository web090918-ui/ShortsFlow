from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.auth as auth_module
import app.processing_jobs as jobs_module
from app.auth import GoogleOAuth, InMemoryUserRepository, SessionSigner
from app.config import get_settings
from app.credits import CreditService, InMemoryCreditLedger, InsufficientCreditsError, minutes_rounded_up
from app.main import app
from app.processing_jobs import InMemoryProcessingJobRepository
from app.ranking import HeuristicRanker
from app.shorts_pipeline import ShortErrorCode, ShortPipelineError


client = TestClient(app)


class FakeOAuth(GoogleOAuth):
    def __init__(self) -> None:
        super().__init__("client-id", "client-secret")

    def exchange_code(self, code: str, *, redirect_uri: str) -> dict:
        return {"id_token": "t"}

    def verify_id_token(self, id_token_value: str) -> dict:
        return {"sub": "sub-credits", "email": "c@example.com", "name": "Credit"}


class StubDispatcher:
    def enqueue(self, job_id, background_tasks) -> str:
        return "task"

    def schedule_resume(self, job_id, *, delay_seconds, sequence) -> str:
        return "resume"


class AllowWorkerAuthenticator:
    def authenticate(self, authorization):
        assert authorization == "Bearer test-token"


@pytest.fixture
def signed_in(monkeypatch):
    service = CreditService(InMemoryCreditLedger(), get_settings())
    monkeypatch.setattr(auth_module, "users", InMemoryUserRepository())
    monkeypatch.setattr(auth_module, "oauth", FakeOAuth())
    monkeypatch.setattr(auth_module, "auth_required", True)
    monkeypatch.setattr(auth_module, "signer", SessionSigner("test-secret"))
    monkeypatch.setattr(auth_module, "credits", service)
    monkeypatch.setattr(jobs_module, "credits", service)
    import app.shorts as shorts_module

    monkeypatch.setattr(shorts_module, "credits", service)
    import app.me as me_module

    monkeypatch.setattr(me_module, "credits", service)
    monkeypatch.setattr(jobs_module, "repository", InMemoryProcessingJobRepository())
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(jobs_module, "worker_authenticator", AllowWorkerAuthenticator())
    monkeypatch.setattr(jobs_module, "candidate_ranker", HeuristicRanker())
    client.cookies.clear()
    start = client.get("/auth/google/start?next=/", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    yield service
    client.cookies.clear()


def test_minutes_round_up() -> None:
    assert minutes_rounded_up(1) == 1
    assert minutes_rounded_up(60) == 1
    assert minutes_rounded_up(61) == 2
    assert minutes_rounded_up(900) == 15


def test_ledger_never_goes_negative_and_keeps_entries() -> None:
    ledger = InMemoryCreditLedger()
    user = uuid4()
    assert ledger.balance(user) is None
    ledger.apply(user, 30, reason="signup")
    ledger.apply(user, -10, reason="analysis", job_id=uuid4())
    with pytest.raises(InsufficientCreditsError) as excinfo:
        ledger.apply(user, -25, reason="short", job_id=uuid4())
    assert excinfo.value.required == 25 and excinfo.value.balance == 20
    assert ledger.balance(user) == 20
    assert [e.delta for e in ledger.entries(user)] == [-10, 30]


def test_signup_grant_once_and_visible_in_status(signed_in) -> None:
    status = client.get("/auth/status").json()
    assert status["credits"] == 30

    summary = client.get("/me/credits").json()
    assert summary["balance"] == 30
    assert summary["costs"]["analysis_per_minute"] == 1
    assert [e["reason"] for e in summary["entries"]] == ["signup"]

    # Logging in again does not grant twice.
    start = client.get("/auth/google/start?next=/", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert client.get("/auth/status").json()["credits"] == 30


def test_analysis_charges_per_source_minute_and_short_render_is_free(signed_in) -> None:
    created = client.post(
        "/processing-jobs",
        json={
            "source_id": str(uuid4()),
            "source_url": "https://youtu.be/abc12345678",
            "start_seconds": 0,
            "end_seconds": 900,
            "rights_confirmed": True,
        },
    )
    assert created.status_code == 202
    assert client.get("/auth/status").json()["credits"] == 15

    manual = client.post(
        "/shorts",
        json={"youtube_url": "https://youtu.be/abc12345678", "start_seconds": 0, "end_seconds": 90, "rights_confirmed": True},
    )
    assert manual.status_code == 202
    assert client.get("/auth/status").json()["credits"] == 13

    entries = client.get("/me/credits").json()["entries"]
    assert [(e["reason"], e["delta"]) for e in entries] == [("short", -2), ("analysis", -15), ("signup", 30)]


def test_insufficient_credits_returns_402_and_charges_nothing(signed_in) -> None:
    response = client.post(
        "/processing-jobs",
        json={
            "source_id": str(uuid4()),
            "source_url": "https://youtu.be/abc12345678",
            "start_seconds": 0,
            "end_seconds": 3600,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 402
    assert "크레딧이 부족합니다" in response.json()["detail"]
    assert client.get("/auth/status").json()["credits"] == 30


def test_terminal_failure_refunds_once(signed_in, monkeypatch, tmp_path) -> None:
    class FailingPipeline:
        def run(self, **kwargs):
            raise ShortPipelineError(ShortErrorCode.FFMPEG_FAILED, "boom", retryable=False)

    monkeypatch.setattr(jobs_module, "short_pipeline", FailingPipeline())
    created = client.post(
        "/shorts",
        json={"youtube_url": "https://youtu.be/abc12345678", "start_seconds": 0, "end_seconds": 60, "rights_confirmed": True},
    ).json()
    assert client.get("/auth/status").json()["credits"] == 29

    first = client.post("/worker/process", json={"job_id": created["id"]}, headers={"Authorization": "Bearer test-token"})
    assert first.json()["status"] == "FAILED"
    assert client.get("/auth/status").json()["credits"] == 30

    # Duplicate delivery of the failed job must not refund again.
    client.post("/worker/process", json={"job_id": created["id"]}, headers={"Authorization": "Bearer test-token"})
    assert client.get("/auth/status").json()["credits"] == 30
    reasons = [e["reason"] for e in client.get("/me/credits").json()["entries"]]
    assert reasons.count("refund") == 1
