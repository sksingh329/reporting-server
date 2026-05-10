from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    get_current_user,
    require_admin,
)
from app.db.session import get_db
from app.schemas.user import UserSettingsOut, UserSettingsUpdate
from app.services import auth_service
from app.schemas.user import (
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/settings", response_model=UserSettingsOut, summary="Get current user's settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> UserSettingsOut:
    return UserSettingsOut.model_validate(auth_service.get_or_create_settings(current_user.id, db))


@router.put("/settings", response_model=UserSettingsOut, summary="Update current user's settings")
def update_settings(
    payload: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> UserSettingsOut:
    if payload.default_project_id is not None:
        from app.db.models import Project
        if db.query(Project).filter(Project.id == payload.default_project_id).first() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found")
    return auth_service.update_settings(current_user.id, payload, db)

# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@router.post(
    "",
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


@router.get("", response_model=list[UserOut], summary="List all users (admin only)")
def list_users(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> list[UserOut]:
    return auth_service.list_users(db)


@router.get("/me", response_model=UserOut, summary="Get current user's profile and role")
def get_me(current_user=Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/{user_id}", response_model=UserOut, summary="Get a user's profile and role (admin only)")
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

@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="Change own password")
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
    "/{user_id}/reset-password",
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

