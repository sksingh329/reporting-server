from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user,
    require_admin,
)
from app.db.session import get_db
from app.schemas.auth import (
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    LoginRequest,
    TokenOut,
    UserCreate,
    UserOut,
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
    return TokenOut(access_token=access_token)


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
    return TokenOut(access_token=access_token)


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
    return TokenOut(access_token=create_access_token(user.username, user.role))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout and revoke refresh token")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if raw:
        auth_service.revoke_refresh_token(raw, db)
    response.delete_cookie(_REFRESH_COOKIE)


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> UserOut:
    existing = auth_service.get_user_by_username(payload.username, db)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    return auth_service.create_user(payload, db)


@router.get("/me", response_model=UserOut, summary="Get current user's profile and role")
def get_me(current_user=Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/users", response_model=list[UserOut], summary="List all users (admin only)")
def list_users(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> list[UserOut]:
    return auth_service.list_users(db)


@router.get("/users/{user_id}", response_model=UserOut, summary="Get a user's profile and role (admin only)")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> UserOut:
    user = auth_service.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, summary="Change own password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    from app.core.security import verify_password
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect")
    auth_service.change_password(current_user, payload.new_password, db)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset any user's password (admin only)",
)
def admin_reset_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> None:
    user = auth_service.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    auth_service.change_password(user, payload.new_password, db)
