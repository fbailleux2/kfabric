from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
from secrets import compare_digest, token_urlsafe
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from kfabric.domain.enums import UserRole
from kfabric.infra.models import Query, User, UserAPIToken, UserWebSession, utcnow


PASSWORD_ITERATIONS = 240_000
SESSION_TOKEN_PREFIX = "kfsess"
API_TOKEN_PREFIX = "kfpat"


@dataclass(frozen=True)
class AuthContext:
    user: User | None = None
    auth_mode: str = "anonymous"
    is_system: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.is_system or self.user is not None

    @property
    def is_admin(self) -> bool:
        if self.is_system:
            return True
        return bool(self.user and self.user.role == UserRole.ADMIN.value and self.user.is_active)

    @property
    def actor_label(self) -> str:
        if self.is_system:
            return "system"
        if self.user is None:
            return "anonymous"
        return self.user.email

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def count_users(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User)) or 0)


def count_active_admins(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN.value,
                User.is_active.is_(True),
            )
        )
        or 0
    )


def has_users(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str | None,
    role: str = UserRole.MEMBER.value,
) -> User:
    normalized_email = normalize_email(email)
    _validate_password(password)
    if db.scalar(select(User.id).where(User.email == normalized_email)):
        raise ValueError(f"User {normalized_email} already exists")

    user = User(
        email=normalized_email,
        display_name=(display_name or normalized_email.split("@", maxsplit=1)[0]).strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def bootstrap_admin(db: Session, *, email: str, password: str, display_name: str | None) -> User:
    if has_users(db):
        raise ValueError("Admin bootstrap is no longer available")
    return create_user(db, email=email, password=password, display_name=display_name, role=UserRole.ADMIN.value)


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    normalized_email = normalize_email(email)
    user = db.scalars(select(User).where(User.email == normalized_email)).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = utcnow()
    db.flush()
    return user


def change_password(user: User, *, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("Current password is invalid")
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)


def set_user_active(user: User, active: bool) -> None:
    user.is_active = active


def create_web_session(
    db: Session,
    *,
    user: User,
    ttl_seconds: int,
) -> tuple[UserWebSession, str]:
    raw_token = _build_secret(SESSION_TOKEN_PREFIX)
    web_session = UserWebSession(
        user_id=user.id,
        session_token_hash=_hash_secret(raw_token),
        expires_at=utcnow() + timedelta(seconds=ttl_seconds),
        last_used_at=utcnow(),
    )
    db.add(web_session)
    db.flush()
    return web_session, raw_token


def resolve_web_session(db: Session, raw_token: str) -> UserWebSession | None:
    if not raw_token:
        return None
    token_hash = _hash_secret(raw_token)
    web_session = db.scalars(select(UserWebSession).where(UserWebSession.session_token_hash == token_hash)).first()
    if web_session is None or web_session.revoked_at is not None:
        return None
    expires_at = _ensure_utc(web_session.expires_at)
    if expires_at < utcnow() or not web_session.user.is_active:
        return None
    web_session.last_used_at = utcnow()
    db.flush()
    return web_session


def revoke_web_session(db: Session, raw_token: str) -> None:
    web_session = resolve_web_session(db, raw_token)
    if web_session is None:
        return
    web_session.revoked_at = utcnow()
    db.flush()


def create_api_token(
    db: Session,
    *,
    user: User,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[UserAPIToken, str]:
    if not name.strip():
        raise ValueError("Token name is required")
    raw_token = _build_secret(API_TOKEN_PREFIX)
    token = UserAPIToken(
        user_id=user.id,
        name=name.strip(),
        token_prefix=raw_token[:18],
        token_hash=_hash_secret(raw_token),
        expires_at=utcnow() + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    db.add(token)
    db.flush()
    return token, raw_token


def resolve_api_token(db: Session, raw_token: str) -> UserAPIToken | None:
    if not raw_token:
        return None
    token_hash = _hash_secret(raw_token)
    token = db.scalars(select(UserAPIToken).where(UserAPIToken.token_hash == token_hash)).first()
    if token is None or token.revoked_at is not None:
        return None
    if token.expires_at and _ensure_utc(token.expires_at) < utcnow():
        return None
    if not token.user.is_active:
        return None
    token.last_used_at = utcnow()
    db.flush()
    return token


def revoke_api_token(token: UserAPIToken) -> None:
    token.revoked_at = utcnow()


def list_user_tokens(db: Session, *, user: User, include_revoked: bool = False) -> list[UserAPIToken]:
    stmt = select(UserAPIToken).where(UserAPIToken.user_id == user.id)
    if not include_revoked:
        stmt = stmt.where(UserAPIToken.revoked_at.is_(None))
    return list(db.scalars(stmt.order_by(UserAPIToken.created_at.desc())))


def build_visibility_clause(principal: AuthContext, query_model: Any = Query):
    owner_column = query_model.owner_user_id
    if principal.is_admin:
        return None
    if principal.user_id:
        return or_(owner_column.is_(None), owner_column == principal.user_id)
    return owner_column.is_(None)


def can_access_query(principal: AuthContext, query: Query) -> bool:
    if principal.is_admin:
        return True
    if query.owner_user_id is None:
        return True
    return principal.user_id == query.owner_user_id


def hash_password(password: str) -> str:
    salt = token_urlsafe(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt, expected = stored_hash.split("$", maxsplit=3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations_str)).hex()
    return compare_digest(candidate, expected)


def serialize_private_token(token: UserAPIToken) -> dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "last_used_at": token.last_used_at,
        "expires_at": token.expires_at,
        "revoked_at": token.revoked_at,
        "created_at": token.created_at,
    }


def _validate_password(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")


def _build_secret(prefix: str) -> str:
    return f"{prefix}_{token_urlsafe(32)}"


def _hash_secret(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
