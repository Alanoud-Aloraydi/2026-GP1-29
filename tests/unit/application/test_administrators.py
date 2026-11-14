"""Tests for granting and revoking administrator access."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from harass.application.accounts.administrators import ManageAdministrators
from harass.application.accounts.errors import (
    RegistrationError,
    UnknownAccountError,
)
from harass.application.accounts.password_policy import PasswordPolicy
from harass.domain.authentication import (
    AuthenticationSession,
    User,
    UserRole,
)
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)

SECURITY = JwtAuthenticationSecurity(
    "isolated-administrator-test-key-at-least-48-bytes-long"
)
NEW_PASSWORD = "a-new-test-only-password-2026"


@pytest.fixture
def store(
    database_factory: sessionmaker[Session],
) -> SqlAlchemyAuthenticationStore:
    """Return the account store over an isolated database."""
    return SqlAlchemyAuthenticationStore(database_factory)


def administrators_for(
    store: SqlAlchemyAuthenticationStore,
) -> ManageAdministrators:
    """Build the administrator service over the account store."""
    return ManageAdministrators(store, SECURITY, PasswordPolicy())


def register(store: SqlAlchemyAuthenticationStore, email: str) -> User:
    """Create an account through the store, as signup does."""
    user = User(str(uuid4()), "Member", email, "synthetic-hash")
    session = AuthenticationSession(
        str(uuid4()), user.user_id, datetime.now(UTC) + timedelta(hours=1)
    )
    assert store.register(user, session)
    return user


def role_of(store: SqlAlchemyAuthenticationStore, user: User) -> UserRole:
    """Read the stored role of an account."""
    stored = store.get_user(user.user_id)
    assert stored is not None
    return stored.role


def test_new_accounts_are_plain_users(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """Signup never produces an administrator."""
    user = register(store, "member@example.test")

    assert role_of(store, user) is UserRole.USER


def test_grant_and_revoke_change_the_stored_role(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """The role persists between reads and can be withdrawn again."""
    user = register(store, "member@example.test")
    administrators = administrators_for(store)

    granted = administrators.grant("member@example.test")

    assert granted.role is UserRole.ADMINISTRATOR
    assert role_of(store, user) is UserRole.ADMINISTRATOR
    assert administrators.revoke("member@example.test").role is UserRole.USER
    assert role_of(store, user) is UserRole.USER


def test_email_is_matched_in_canonical_form(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """Case and surrounding spaces do not hide an account."""
    user = register(store, "member@example.test")

    administrators_for(store).grant("  Member@Example.TEST ")

    assert role_of(store, user) is UserRole.ADMINISTRATOR


def test_granting_to_an_unknown_email_changes_nothing(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """A mistyped email fails instead of creating or promoting anyone."""
    user = register(store, "member@example.test")

    with pytest.raises(UnknownAccountError):
        administrators_for(store).grant("other@example.test")

    assert role_of(store, user) is UserRole.USER


def test_setting_the_role_of_a_missing_account_reports_false(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """The store says so when no row was changed."""
    assert store.set_role(str(uuid4()), UserRole.ADMINISTRATOR) is False


def test_database_rejects_an_unknown_role(
    database_factory: sessionmaker[Session],
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """The database is the last line of defence against a bad role."""
    user = register(store, "member@example.test")

    with (
        pytest.raises(IntegrityError),
        database_factory() as database,
        database.begin(),
    ):
        database.execute(
            text("UPDATE users SET role = 'root' WHERE user_id = :id"),
            {"id": user.user_id},
        )


def test_reset_password_replaces_the_password_and_ends_sessions(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """The new password works and no earlier session survives the reset."""
    user = register(store, "member@example.test")
    assert store.list_sessions(user.user_id)

    administrators_for(store).reset_password(
        "  Member@Example.TEST ", NEW_PASSWORD
    )

    stored = store.get_user(user.user_id)
    assert stored is not None
    assert SECURITY.verify_password(NEW_PASSWORD, stored.password_hash)
    assert store.list_sessions(user.user_id) == []


def test_reset_password_rejects_a_weak_password_without_changes(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """A password below the policy leaves the account untouched."""
    user = register(store, "member@example.test")

    with pytest.raises(RegistrationError):
        administrators_for(store).reset_password(
            "member@example.test", "too-short"
        )

    stored = store.get_user(user.user_id)
    assert stored is not None
    assert stored.password_hash == "synthetic-hash"
    assert store.list_sessions(user.user_id)


def test_reset_password_for_an_unknown_email_fails(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """A mistyped email resets nobody."""
    with pytest.raises(UnknownAccountError):
        administrators_for(store).reset_password(
            "other@example.test", NEW_PASSWORD
        )


def test_setting_the_password_of_a_missing_account_reports_false(
    store: SqlAlchemyAuthenticationStore,
) -> None:
    """The store says so when no row was changed."""
    assert store.set_password(str(uuid4()), "new-hash") is False
