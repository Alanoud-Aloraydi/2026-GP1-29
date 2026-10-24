"""Consume account actions atomically and revoke stale credentials."""

import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from harass.application.ports.account_actions import AccountActionStore
from harass.domain.account_action import AccountAction, AccountActionPurpose
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    AccountActionRow,
    AuthenticationSessionRow,
    UserRow,
)


class SqlAlchemyAccountActionStore(AccountActionStore):
    """Serialize account changes and enforce single-use token consumption."""

    def __init__(self, factory: SessionFactory) -> None:
        """Bind the database-session factory."""
        self._factory = factory

    def issue(self, action: AccountAction) -> bool:
        """Replace an earlier action only for unchanged account credentials."""
        with self._factory() as database, database.begin():
            user = database.get(UserRow, action.user_id, with_for_update=True)
            if user is None or not hmac.compare_digest(
                _fingerprint(user.password_hash), action.credential_hash
            ):
                return False
            database.execute(
                delete(AccountActionRow).where(
                    (AccountActionRow.expires_at <= datetime.now(UTC))
                    | (
                        (AccountActionRow.user_id == user.user_id)
                        & (AccountActionRow.purpose == action.purpose.value)
                    )
                )
            )
            database.add(
                AccountActionRow(
                    action_id=action.action_id,
                    user_id=action.user_id,
                    purpose=action.purpose.value,
                    token_hash=action.token_hash,
                    credential_hash=action.credential_hash,
                    expires_at=action.expires_at,
                )
            )
        return True

    def verify_email(self, digest: str, now: datetime) -> bool:
        """Consume verification and persist the verified-email state."""
        return self._consume(digest, now, AccountActionPurpose.VERIFY_EMAIL)

    def reset_password(
        self, digest: str, password_hash: str, now: datetime
    ) -> bool:
        """Change credentials and revoke sessions in the token transaction."""
        return self._consume(
            digest, now, AccountActionPurpose.RESET_PASSWORD, password_hash
        )

    def _consume(
        self,
        digest: str,
        now: datetime,
        purpose: AccountActionPurpose,
        password_hash: str | None = None,
    ) -> bool:
        """Lock the owner before claiming a purpose-bound token by deletion."""
        with self._factory() as database, database.begin():
            owner = database.scalar(
                select(AccountActionRow.user_id).where(
                    AccountActionRow.token_hash == digest
                )
            )
            if owner is None:
                return False
            user = database.get(UserRow, owner, with_for_update=True)
            if user is None:
                return False
            claimed = database.scalar(
                delete(AccountActionRow)
                .where(
                    AccountActionRow.token_hash == digest,
                    AccountActionRow.purpose == purpose.value,
                    AccountActionRow.expires_at > now,
                    AccountActionRow.credential_hash
                    == _fingerprint(user.password_hash),
                )
                .returning(AccountActionRow.action_id)
            )
            if claimed is None:
                return False
            return _update_account(database, user, password_hash)


def _fingerprint(password_hash: str) -> str:
    """Bind actions to a credential version without storing its raw hash."""
    return hashlib.sha256(password_hash.encode()).hexdigest()


def _update_account(
    database: Session, user: UserRow, password_hash: str | None
) -> bool:
    """Apply a guarded account change and revoke reset-related state."""
    changed = database.scalar(
        update(UserRow)
        .where(
            UserRow.user_id == user.user_id,
            UserRow.password_hash == user.password_hash,
        )
        .values(
            {"password_hash": password_hash}
            if password_hash is not None
            else {"email_verified": True}
        )
        .returning(UserRow.user_id)
    )
    if changed is None:
        return False
    if password_hash is not None:
        database.execute(
            delete(AuthenticationSessionRow).where(
                AuthenticationSessionRow.user_id == user.user_id
            )
        )
        database.execute(
            delete(AccountActionRow).where(
                AccountActionRow.user_id == user.user_id
            )
        )
    return True
