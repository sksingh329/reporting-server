from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
)
from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    TokenOut,
)
from app.schemas.user import (
    UserCreate,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_COOKIE_OPTS = dict(httponly=True, samesite="lax", secure=False)  # set secure=True behind HTTPS


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

@router.post(
    "/bootstrap",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create the first admin user (only works when no users exist)",
)
def bootstrap(payload: UserCreate, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    if auth_service.user_count(db) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap already done — users already exist",
        )
    payload.role = "admin"
    user = auth_service.create_user(payload, db)
    access_token = create_access_token(user.username, user.role)
    raw_refresh = auth_service.create_refresh_token(user.id, db)
    response.set_cookie(_REFRESH_COOKIE, raw_refresh, **_COOKIE_OPTS)
    return TokenOut(access_token=access_token, expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60)


# ---------------------------------------------------------------------------
# Login / logout / refresh
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenOut, summary="Login and get access token")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    user = auth_service.authenticate_user(payload.username, payload.password, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(user.username, user.role)
    raw_refresh = auth_service.create_refresh_token(user.id, db)
    response.set_cookie(_REFRESH_COOKIE, raw_refresh, **_COOKIE_OPTS)
    return TokenOut(access_token=access_token, expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60)


@router.post("/refresh", response_model=TokenOut, summary="Get a new access token using refresh token cookie")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    user = auth_service.validate_refresh_token(raw, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    # Rotate: revoke old, issue new
    auth_service.revoke_refresh_token(raw, db)
    new_raw = auth_service.create_refresh_token(user.id, db)
    response.set_cookie(_REFRESH_COOKIE, new_raw, **_COOKIE_OPTS)
    return TokenOut(access_token=create_access_token(user.username, user.role), expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout and revoke refresh token")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if raw:
        auth_service.revoke_refresh_token(raw, db)
    response.delete_cookie(_REFRESH_COOKIE)
