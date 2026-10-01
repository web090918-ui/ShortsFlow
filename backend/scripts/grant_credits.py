"""Grant (or deduct) credits for one account by email or user id.

Runs against whatever ledger the SHORTSFLOW_* settings point at. With the Firestore
backend this needs Application Default Credentials for the project, e.g.

    gcloud auth application-default login
    SHORTSFLOW_JOB_REPOSITORY_BACKEND=firestore SHORTSFLOW_GCP_PROJECT_ID=<id> \\
    SHORTSFLOW_FIRESTORE_DATABASE=shortflow \\
    python scripts/grant_credits.py --email someone@example.com --amount 1000

The in-memory backend only lives inside a running server process, so this script
refuses it rather than pretending the grant stuck. Every grant is written as an
"adjustment" ledger entry so it shows up in the account's credit history.
"""

import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.config import get_settings  # noqa: E402
from app.credits import credit_ledger_from_settings  # noqa: E402


def _find_user_id(client, *, email: str) -> UUID:
    from google.cloud.firestore_v1 import FieldFilter

    query = client.collection("users").where(filter=FieldFilter("email", "==", email)).limit(2)
    docs = list(query.stream())
    if not docs:
        raise SystemExit(f"No user with email {email}")
    if len(docs) > 1:
        raise SystemExit(f"{len(docs)} users share {email}; pass --user-id instead")
    return UUID(str(docs[0].to_dict()["id"]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--email")
    who.add_argument("--user-id", type=UUID)
    parser.add_argument(
        "--amount", type=int, required=True, help="positive to grant, negative to deduct"
    )
    parser.add_argument("--note", default="운영자 조정")
    args = parser.parse_args()

    settings = get_settings()
    if settings.job_repository_backend != "firestore":
        raise SystemExit(
            "SHORTSFLOW_JOB_REPOSITORY_BACKEND must be 'firestore'; the memory ledger "
            "exists only inside a running server."
        )
    from google.cloud import firestore

    client = firestore.Client(
        project=settings.gcp_project_id, database=settings.firestore_database
    )
    user_id = args.user_id or _find_user_id(client, email=args.email)
    ledger = credit_ledger_from_settings(settings)
    before = ledger.balance(user_id) or 0
    entry = ledger.apply(user_id, args.amount, reason="adjustment", note=args.note)
    print(f"user {user_id}: {before} -> {entry.balance_after} credits ({args.amount:+d})")


if __name__ == "__main__":
    main()
