from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import AuthPrincipal, get_auth_principal
from app.db.session import get_db
from app.schemas.auth import ServiceTokenCreate, ServiceTokenListItem, ServiceTokenOut
from app.services import auth_service

router = APIRouter(prefix="/api/service-tokens", tags=["service-tokens"])


@router.post("", response_model=ServiceTokenOut, status_code=status.HTTP_201_CREATED, summary="Create a service token [any · JWT/token]",
    description="The new token inherits the caller's role. Token value is returned **once only** — store it immediately.")
def create_service_token(
    payload: ServiceTokenCreate,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> ServiceTokenOut:
    created_by_user_id = None if principal.is_service_token else principal.id
    raw, token = auth_service.create_service_token(
        name=payload.name,
        role=principal.role,
        db=db,
        expires_at=payload.expires_at,
        created_by_user_id=created_by_user_id,
    )
    out = ServiceTokenOut.model_validate(token)
    out.token = raw
    return out


@router.get("", response_model=list[ServiceTokenListItem], summary="List service tokens",
    description="**Required role:** any authenticated user or service token\n\nAdmins see all tokens. Regular users see only the tokens they created.\n\nUse `include_inactive=true` (admin only) to include revoked tokens.")
def list_service_tokens(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
    include_inactive: bool = Query(False, description="Include revoked tokens (admin only)"),
) -> list[ServiceTokenListItem]:
    if principal.role == "admin":
        tokens = auth_service.list_service_tokens(db, include_inactive=include_inactive)
    elif principal.is_service_token:
        tokens = []
    else:
        tokens = auth_service.list_service_tokens(db, created_by_user_id=principal.id)
    return [ServiceTokenListItem.model_validate(t) for t in tokens]
    return [ServiceTokenListItem.model_validate(t) for t in tokens]


@router.get("/{token_id}", response_model=ServiceTokenListItem, summary="Get a service token [owner/admin · JWT/token]")
def get_service_token(
    token_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> ServiceTokenListItem:
    token = auth_service.get_service_token(token_id, db)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if principal.role != "admin" and token.created_by_user_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return ServiceTokenListItem.model_validate(token)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a service token [owner/admin · JWT/token]")
def revoke_service_token(
    token_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> None:
    token = auth_service.get_service_token(token_id, db)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if principal.role != "admin" and token.created_by_user_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    auth_service.revoke_service_token(token_id, db)
