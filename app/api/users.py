from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.auth import UserSettingsOut, UserSettingsUpdate
from app.services import auth_service

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
