"""Task 12A: Google sign-in and HttpOnly session cookies.

The browser talks to this API through a same-origin ``/api`` rewrite, so the
session cookie is first-party. Only Google OAuth is offered; the same Google
identity later carries the YouTube channel connection (Task 12B).
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request as HttpRequest, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "openid email profile"


class UserRecord(BaseModel):
    id: UUID
    google_sub: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    created_at: datetime
    last_login_at: datetime


class UserResponse(BaseModel):
    id: UUID
    email: str | None
    name: str | None
    picture: str | None


class AuthStatus(BaseModel):
    auth_required: bool
    login_available: bool
    user: UserResponse | None


class UserRepository(Protocol):
    def get(self, user_id: UUID) -> UserRecord | None: ...

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None: ...

    def save(self, user: UserRecord) -> UserRecord: ...


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[UUID, UserRecord] = {}
        self._lock = threading.Lock()

    def get(self, user_id: UUID) -> UserRecord | None:
        with self._lock:
            return self._users.get(user_id)

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None:
        with self._lock:
            return next((u for u in self._users.values() if u.google_sub == google_sub), None)

    def save(self, user: UserRecord) -> UserRecord:
        with self._lock:
            self._users[user.id] = user
        return user


class FirestoreUserRepository:
    def __init__(self, client: Any, collection: str = "users") -> None:
        self._collection = client.collection(collection)

    def get(self, user_id: UUID) -> UserRecord | None:
        snapshot = self._collection.document(str(user_id)).get()
        return UserRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None:
        from google.cloud.firestore_v1 import FieldFilter

        query = self._collection.where(filter=FieldFilter("google_sub", "==", google_sub)).limit(1)
        for snapshot in query.stream():
            return UserRecord.model_validate(snapshot.to_dict())
        return None

    def save(self, user: UserRecord) -> UserRecord:
        self._collection.document(str(user.id)).set(user.model_dump(mode="json"))
        return user


class SessionSigner:
    """Compact HMAC-signed JSON tokens for the session cookie and OAuth state."""

    def __init__(self, secret: str) -> None:
        self._key = secret.encode("utf-8")

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64(data: str) -> bytes:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    def sign(self, payload: dict[str, Any], *, ttl_seconds: int) -> str:
        body = dict(payload)
        body["exp"] = int(time.time()) + ttl_seconds
        encoded = self._b64(json.dumps(body, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{self._b64(signature)}"

    def verify(self, token: str | None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None
        encoded, _, signature = token.rpartition(".")
        expected = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
        try:
            if not hmac.compare_digest(self._unb64(signature), expected):
                return None
            payload = json.loads(self._unb64(encoded).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
            return None
        return payload


class GoogleOAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, *, redirect_uri: str) -> dict[str, Any]:
        body = urlencode(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self._client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        request = Request(
            GOOGLE_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or "id_token" not in payload:
            raise ValueError("Google token response had no id_token")
        return payload

    def verify_id_token(self, id_token_value: str) -> dict[str, Any]:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            id_token_value, google_requests.Request(), audience=self.client_id
        )
        if not claims.get("sub"):
            raise ValueError("Google ID token had no subject")
        return claims


def _user_repository_from_settings(settings: Settings) -> UserRepository:
    if settings.job_repository_backend == "memory":
        return InMemoryUserRepository()
    from google.cloud import firestore

    return FirestoreUserRepository(
        firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    )


def _oauth_from_settings(settings: Settings) -> GoogleOAuth | None:
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        return GoogleOAuth(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret.get_secret_value(),
        )
    return None


settings = get_settings()
auth_required: bool = settings.auth_mode == "google"
users: UserRepository = _user_repository_from_settings(settings)
oauth: GoogleOAuth | None = _oauth_from_settings(settings)
signer = SessionSigner(
    settings.session_secret.get_secret_value()
    if settings.session_secret
    else "development-only-session-secret"
)
if auth_required and (oauth is None or settings.session_secret is None):
    # Fail closed but keep serving: creation stays blocked (login required) and
    # /auth/status reports login_available=false so the misconfiguration is visible
    # instead of a revision that never starts.
    logger.critical(
        "SHORTSFLOW_AUTH_MODE=google but SHORTSFLOW_GOOGLE_OAUTH_CLIENT_ID, "
        "SHORTSFLOW_GOOGLE_OAUTH_CLIENT_SECRET, or SHORTSFLOW_SESSION_SECRET is missing; "
        "sign-in is unavailable until they are set."
    )
    oauth = None

router = APIRouter(prefix="/auth", tags=["auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _redirect_uri() -> str:
    return f"{settings.app_public_origin.rstrip('/')}{settings.api_public_prefix}/auth/google/callback"


def _safe_next(value: str | None) -> str:
    """Only same-site relative paths may be used as the post-login destination."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _cookie_secure() -> bool:
    return urlparse(settings.app_public_origin).scheme == "https"


def _set_session_cookie(response: Response, user: UserRecord) -> None:
    token = signer.sign({"uid": str(user.id)}, ttl_seconds=settings.session_ttl_seconds)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def current_user(request: HttpRequest) -> UserRecord | None:
    payload = signer.verify(request.cookies.get(settings.session_cookie_name))
    if payload is None:
        return None
    try:
        user_id = UUID(str(payload.get("uid")))
    except ValueError:
        return None
    return users.get(user_id)


def require_user(user: UserRecord | None = Depends(current_user)) -> UserRecord | None:
    """Enforce login when auth mode is google; pass through in development."""
    if auth_required and user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    return user


def _to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name, picture=user.picture)


@router.get("/status", response_model=AuthStatus)
def auth_status(user: UserRecord | None = Depends(current_user)) -> AuthStatus:
    return AuthStatus(
        auth_required=auth_required,
        login_available=oauth is not None,
        user=_to_user_response(user) if user else None,
    )


@router.get("/me", response_model=UserResponse)
def me(user: UserRecord | None = Depends(current_user)) -> UserResponse:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    return _to_user_response(user)


@router.get("/google/start")
def google_start(next: str | None = None) -> RedirectResponse:
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google 로그인이 설정되지 않았습니다."
        )
    state = signer.sign({"n": secrets.token_urlsafe(16), "next": _safe_next(next)}, ttl_seconds=600)
    return RedirectResponse(
        oauth.authorization_url(redirect_uri=_redirect_uri(), state=state),
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/google/callback")
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if oauth is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google 로그인이 설정되지 않았습니다.")
    state_payload = signer.verify(state)
    if state_payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="로그인 상태가 만료되었습니다. 다시 시도해 주세요.")
    destination = _safe_next(state_payload.get("next"))
    if error or not code:
        return RedirectResponse(f"{destination}?login=cancelled", status_code=status.HTTP_302_FOUND)
    try:
        tokens = oauth.exchange_code(code, redirect_uri=_redirect_uri())
        claims = oauth.verify_id_token(str(tokens["id_token"]))
    except Exception as exc:
        logger.warning("Google sign-in failed", exc_info=exc)
        return RedirectResponse(f"{destination}?login=failed", status_code=status.HTTP_302_FOUND)

    now = _now()
    user = users.get_by_google_sub(str(claims["sub"]))
    if user is None:
        user = UserRecord(
            id=uuid4(),
            google_sub=str(claims["sub"]),
            email=claims.get("email"),
            name=claims.get("name"),
            picture=claims.get("picture"),
            created_at=now,
            last_login_at=now,
        )
    else:
        user = user.model_copy(
            update={
                "email": claims.get("email") or user.email,
                "name": claims.get("name") or user.name,
                "picture": claims.get("picture") or user.picture,
                "last_login_at": now,
            }
        )
    users.save(user)
    response = RedirectResponse(destination, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, user)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
