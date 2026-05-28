from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator

class AdminResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Literal["admin", "user"] = "user"

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserSettingsOut(BaseModel):
    user_id: int
    app_theme: str
    log_popup_theme: str
    timezone: str
    default_project_id: Optional[int]
    duration_unit: str

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    app_theme: Optional[Literal["light", "dark"]] = None
    log_popup_theme: Optional[Literal["light", "dark"]] = None
    timezone: Optional[str] = None
    default_project_id: Optional[int] = None
    duration_unit: Optional[Literal["ms", "s"]] = None
