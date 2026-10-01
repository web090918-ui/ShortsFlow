"""Per-account credits: a signup grant, a charge per created job, and automatic
refunds when a job fails for good.

Balances live in ``credit_balances/{user_id}`` and every change is appended to
``credit_entries`` so the account page can show a ledger. Firestore writes use a
transaction so concurrent requests cannot drive a balance negative.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.config import Settings


CreditReason = Literal[
    "signup", "analysis", "short", "product_short", "refund", "purchase", "adjustment"
]


class CreditEntry(BaseModel):
    id: UUID
    user_id: UUID
    delta: int
    reason: CreditReason
    job_id: UUID | None = None
    note: str | None = None
    balance_after: int
    created_at: datetime


class InsufficientCreditsError(Exception):
    def __init__(self, *, required: int, balance: int) -> None:
        super().__init__(f"크레딧이 부족합니다 (필요 {required}, 보유 {balance}).")
        self.required = required
        self.balance = balance


class CreditLedger(Protocol):
    def balance(self, user_id: UUID) -> int | None:
        """Current balance, or None when the account has never been granted credits."""
        ...

    def apply(
        self,
        user_id: UUID,
        delta: int,
        *,
        reason: CreditReason,
        job_id: UUID | None = None,
        note: str | None = None,
    ) -> CreditEntry: ...

    def entries(self, user_id: UUID, *, limit: int = 50) -> list[CreditEntry]: ...

    def refunded(self, job_id: UUID) -> bool: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryCreditLedger:
    def __init__(self) -> None:
        self._balances: dict[UUID, int] = {}
        self._entries: list[CreditEntry] = []
        self._lock = threading.Lock()

    def balance(self, user_id: UUID) -> int | None:
        with self._lock:
            return self._balances.get(user_id)

    def apply(self, user_id, delta, *, reason, job_id=None, note=None) -> CreditEntry:
        with self._lock:
            current = self._balances.get(user_id, 0)
            if current + delta < 0:
                raise InsufficientCreditsError(required=-delta, balance=current)
            current += delta
            self._balances[user_id] = current
            entry = CreditEntry(
                id=uuid4(), user_id=user_id, delta=delta, reason=reason, job_id=job_id,
                note=note, balance_after=current, created_at=_now(),
            )
            self._entries.append(entry)
            return entry

    def entries(self, user_id: UUID, *, limit: int = 50) -> list[CreditEntry]:
        with self._lock:
            mine = [entry for entry in self._entries if entry.user_id == user_id]
        mine.sort(key=lambda entry: entry.created_at, reverse=True)
        return mine[:limit]

    def refunded(self, job_id: UUID) -> bool:
        with self._lock:
            return any(e.job_id == job_id and e.reason == "refund" for e in self._entries)


class FirestoreCreditLedger:
    def __init__(self, client: Any) -> None:
        self._client = client
        self._balances = client.collection("credit_balances")
        self._entries = client.collection("credit_entries")

    def balance(self, user_id: UUID) -> int | None:
        snapshot = self._balances.document(str(user_id)).get()
        if not snapshot.exists:
            return None
        return int((snapshot.to_dict() or {}).get("balance", 0))

    def apply(self, user_id, delta, *, reason, job_id=None, note=None) -> CreditEntry:
        from google.cloud import firestore

        balance_ref = self._balances.document(str(user_id))
        transaction = self._client.transaction()

        @firestore.transactional
        def run(transaction: Any) -> CreditEntry:
            snapshot = balance_ref.get(transaction=transaction)
            current = int((snapshot.to_dict() or {}).get("balance", 0)) if snapshot.exists else 0
            if current + delta < 0:
                raise InsufficientCreditsError(required=-delta, balance=current)
            current += delta
            entry = CreditEntry(
                id=uuid4(), user_id=user_id, delta=delta, reason=reason, job_id=job_id,
                note=note, balance_after=current, created_at=_now(),
            )
            transaction.set(balance_ref, {"balance": current, "updated_at": entry.created_at.isoformat()})
            transaction.set(self._entries.document(str(entry.id)), entry.model_dump(mode="json"))
            return entry

        return run(transaction)

    def entries(self, user_id: UUID, *, limit: int = 50) -> list[CreditEntry]:
        from google.cloud.firestore_v1 import FieldFilter

        query = self._entries.where(filter=FieldFilter("user_id", "==", str(user_id))).limit(500)
        found = [CreditEntry.model_validate(s.to_dict()) for s in query.stream()]
        found.sort(key=lambda entry: entry.created_at, reverse=True)
        return found[:limit]

    def refunded(self, job_id: UUID) -> bool:
        from google.cloud.firestore_v1 import FieldFilter

        query = (
            self._entries.where(filter=FieldFilter("job_id", "==", str(job_id)))
            .where(filter=FieldFilter("reason", "==", "refund"))
            .limit(1)
        )
        return any(True for _ in query.stream())


def credit_ledger_from_settings(settings: Settings) -> CreditLedger:
    if settings.job_repository_backend == "memory":
        return InMemoryCreditLedger()
    from google.cloud import firestore

    return FirestoreCreditLedger(
        firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    )


def minutes_rounded_up(seconds: float) -> int:
    return max(1, -(-int(round(seconds)) // 60))


class CreditService:
    """Policy layer: what each action costs and when the signup grant applies.

    One credit is one minute of source video analysed, the unit every competitor
    uses (Vizard, 2short, EasyCut, FikaClip), because source length is also what
    drives our own acquisition, transcription, and compute cost.
    """

    def __init__(self, ledger: CreditLedger, settings: Settings) -> None:
        self.ledger = ledger
        self.signup_grant = settings.credit_signup_grant
        self.analysis_per_minute = settings.credit_analysis_per_minute
        self.manual_short_per_minute = settings.credit_manual_short_per_minute
        self.candidate_render_cost = settings.credit_candidate_render
        self.product_short_cost = settings.credit_product_short

    def ensure_signup_grant(self, user_id: UUID) -> int:
        """Grant once per account; accounts created before credits existed get it on next login."""
        current = self.ledger.balance(user_id)
        if current is None:
            return self.ledger.apply(
                user_id, self.signup_grant, reason="signup", note="가입 보너스"
            ).balance_after
        return current

    def analysis_cost(self, duration_seconds: float) -> int:
        return minutes_rounded_up(duration_seconds) * self.analysis_per_minute

    def short_cost(self, duration_seconds: float, *, from_candidate: bool) -> int:
        if from_candidate:
            return self.candidate_render_cost
        return minutes_rounded_up(duration_seconds) * self.manual_short_per_minute

    def product_cost(self) -> int:
        return self.product_short_cost

    def charge(self, user_id: UUID, cost: int, *, reason: CreditReason, job_id: UUID, note: str | None = None) -> int:
        if cost <= 0:
            return 0
        self.ledger.apply(user_id, -cost, reason=reason, job_id=job_id, note=note)
        return cost

    def refund(self, user_id: UUID, amount: int, *, job_id: UUID, note: str | None = None) -> None:
        if amount <= 0 or self.ledger.refunded(job_id):
            return
        self.ledger.apply(user_id, amount, reason="refund", job_id=job_id, note=note or "작업 실패 환불")
