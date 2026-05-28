from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_refresh_token_value
from app.core.config import settings
from app.db.models import RefreshToken, ServiceToken, User, UserSettings
from app.schemas.user import UserCreate, UserOut, UserSettingsOut, UserSettingsUpdate


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def user_count(db: Session) -> int:
    return db.query(User).count()


def get_user_by_username(username: str, db: Session) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(user_id: int, db: Session) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.id).all()]


def create_user(payload: UserCreate, db: Session) -> UserOut:
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)

def delete_user(user: User, db: Session) -> None:
    db.delete(user)
    db.commit()


def authenticate_user(username: str, password: str, db: Session) -> Optional[User]:
    user = get_user_by_username(username, db)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def change_password(user: User, new_password: str, db: Session) -> None:
    user.hashed_password = hash_password(new_password)
    db.commit()
    # Revoke all refresh tokens so existing sessions are invalidated
    revoke_all_refresh_tokens(user.id, db)


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_refresh_token(user_id: int, db: Session) -> str:
    """Create, store (hashed), and return the raw refresh token value."""
    raw = create_refresh_token_value()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=expires_at,
    ))
    db.commit()
    return raw


def validate_refresh_token(raw: str, db: Session) -> Optional[User]:
    """Validate the raw refresh token and return the associated User, or None."""
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _hash_token(raw),
        RefreshToken.revoked == False,  # noqa: E712
    ).first()
    if record is None:
        return None
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    return record.user


def revoke_refresh_token(raw: str, db: Session) -> None:
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _hash_token(raw),
    ).first()
    if record:
        record.revoked = True
        db.commit()


def revoke_all_refresh_tokens(user_id: int, db: Session) -> None:
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update({"revoked": True})
    db.commit()


# ---------------------------------------------------------------------------
# User settings helpers
# ---------------------------------------------------------------------------

def get_or_create_settings(user_id: int, db: Session) -> UserSettings:
    record = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if record is None:
        record = UserSettings(user_id=user_id)
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def update_settings(user_id: int, payload: UserSettingsUpdate, db: Session) -> UserSettingsOut:
    record = get_or_create_settings(user_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return UserSettingsOut.model_validate(record)


# ---------------------------------------------------------------------------
# Service token helpers
# ---------------------------------------------------------------------------

_SERVICE_TOKEN_PREFIX = "rpt_"


def _generate_service_token() -> str:
    return _SERVICE_TOKEN_PREFIX + secrets.token_urlsafe(48)


def create_service_token(
    name: str,
    role: str,
    db: Session,
    expires_at: Optional[datetime] = None,
    created_by_user_id: Optional[int] = None,
) -> tuple[str, ServiceToken]:
    """Generate a new service token, store its hash, return (raw_value, ORM record)."""
    raw = _generate_service_token()
    token = ServiceToken(
        name=name,
        role=role,
        token_hash=_hash_token(raw),
        expires_at=expires_at,
        created_by_user_id=created_by_user_id,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return raw, token


def validate_service_token(raw: str, db: Session) -> Optional[ServiceToken]:
    """Validate a raw service token string. Updates last_used_at on success."""
    record = db.query(ServiceToken).filter(
        ServiceToken.token_hash == _hash_token(raw),
        ServiceToken.is_active == True,  # noqa: E712
    ).first()
    if record is None:
        return None
    if record.expires_at is not None:
        expires = record.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
    record.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return record


def list_service_tokens(
    db: Session,
    created_by_user_id: Optional[int] = None,
    include_inactive: bool = False,
) -> list[ServiceToken]:
    query = db.query(ServiceToken)
    if not include_inactive:
        query = query.filter(ServiceToken.is_active == True)  # noqa: E712
    if created_by_user_id is not None:
        query = query.filter(ServiceToken.created_by_user_id == created_by_user_id)
    return query.order_by(ServiceToken.id).all()


def get_service_token(token_id: int, db: Session) -> Optional[ServiceToken]:
    return db.query(ServiceToken).filter(ServiceToken.id == token_id).first()


def revoke_service_token(token_id: int, db: Session) -> bool:
    record = db.query(ServiceToken).filter(ServiceToken.id == token_id).first()
    if record is None:
        return False
    record.is_active = False
    db.commit()
    return True
