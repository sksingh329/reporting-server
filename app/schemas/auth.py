from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


# ---------------------------------------------------------------------------
# Service token schemas
# ---------------------------------------------------------------------------

class ServiceTokenCreate(BaseModel):
    name: str
    expires_at: Optional[datetime] = None


class ServiceTokenOut(BaseModel):
    id: int
    name: str
    role: str
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    owner_id: Optional[int] = Field(None, validation_alias="created_by_user_id")
    token: Optional[str] = None  # only present in the creation response

    model_config = {"from_attributes": True, "populate_by_name": True}


class ServiceTokenListItem(BaseModel):
    id: int
    name: str
    role: str
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    owner_id: Optional[int] = Field(None, validation_alias="created_by_user_id")

    model_config = {"from_attributes": True, "populate_by_name": True}
