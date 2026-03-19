from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric.api.deps import (
    WEB_SESSION_COOKIE,
    auth_bootstrap_required,
    get_db,
    get_request_principal,
    get_runtime_settings,
    require_admin_principal,
    require_authenticated_principal,
)
from kfabric.api.serializers import (
    serialize_auth_session,
    serialize_user,
    serialize_user_token,
    serialize_user_token_create,
)
from kfabric.config import AppSettings
from kfabric.domain.schemas import (
    AuthBootstrapRequest,
    AuthSessionResponse,
    LoginRequest,
    PasswordChangeRequest,
    UserCreateRequest,
    UserResponse,
    UserStatusUpdateResponse,
    UserTokenCreateRequest,
    UserTokenCreateResponse,
    UserTokenResponse,
)
from kfabric.infra.models import User, UserAPIToken
from kfabric.services.auth_service import (
    AuthContext,
    authenticate_user,
    bootstrap_admin,
    change_password,
    count_active_admins,
    create_api_token,
    create_user,
    create_web_session,
    list_user_tokens,
    revoke_api_token,
    revoke_web_session,
    set_user_active,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-admin", response_model=AuthSessionResponse)
def bootstrap_first_admin(
    request: Request,
    payload: AuthBootstrapRequest,
    response: Response,
    bootstrap_required: bool = Depends(auth_bootstrap_required),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> AuthSessionResponse:
    if not bootstrap_required:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin bootstrap is disabled")
    user = bootstrap_admin(db, email=payload.email, password=payload.password, display_name=payload.display_name)
    web_session, raw_token = create_web_session(db, user=user, ttl_seconds=settings.session_ttl_seconds)
    db.commit()
    _set_session_cookie(response, request=request, raw_token=raw_token, max_age=settings.session_ttl_seconds)
    return serialize_auth_session(user, "bootstrap", web_session.expires_at)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> AuthSessionResponse:
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    web_session, raw_token = create_web_session(db, user=user, ttl_seconds=settings.session_ttl_seconds)
    db.commit()
    _set_session_cookie(response, request=request, raw_token=raw_token, max_age=settings.session_ttl_seconds)
    return serialize_auth_session(user, "password", web_session.expires_at)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    session_token = request.cookies.get(WEB_SESSION_COOKIE)
    if session_token:
        revoke_web_session(db, session_token)
        db.commit()
    response.delete_cookie(WEB_SESSION_COOKIE, httponly=True, samesite="strict")
    return {"status": "signed_out"}


@router.get("/me", response_model=UserResponse)
def me(principal: AuthContext = Depends(require_authenticated_principal)) -> UserResponse:
    user = _require_user_principal(principal)
    return serialize_user(user)


@router.get("/users", response_model=list[UserResponse], dependencies=[Depends(require_admin_principal)])
def list_users(db: Session = Depends(get_db)) -> list[UserResponse]:
    users = list(db.scalars(select(User).order_by(User.created_at.asc())))
    return [serialize_user(user) for user in users]


@router.post("/users", response_model=UserResponse, dependencies=[Depends(require_admin_principal)])
def create_user_account(payload: UserCreateRequest, db: Session = Depends(get_db)) -> UserResponse:
    user = create_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role.value,
    )
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.post("/users/{user_id}:activate", response_model=UserStatusUpdateResponse, dependencies=[Depends(require_admin_principal)])
def activate_user(user_id: str, db: Session = Depends(get_db)) -> UserStatusUpdateResponse:
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    set_user_active(user, True)
    db.commit()
    db.refresh(user)
    return UserStatusUpdateResponse(user=serialize_user(user))


@router.post("/users/{user_id}:deactivate", response_model=UserStatusUpdateResponse, dependencies=[Depends(require_admin_principal)])
def deactivate_user(user_id: str, db: Session = Depends(get_db)) -> UserStatusUpdateResponse:
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    if user.role == "admin" and user.is_active and count_active_admins(db) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="At least one active admin must remain")
    set_user_active(user, False)
    db.commit()
    db.refresh(user)
    return UserStatusUpdateResponse(user=serialize_user(user))


@router.post("/change-password")
def update_password(
    payload: PasswordChangeRequest,
    principal: AuthContext = Depends(require_authenticated_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _require_user_principal(principal)
    change_password(user, current_password=payload.current_password, new_password=payload.new_password)
    db.commit()
    return {"status": "password_updated"}


@router.get("/tokens", response_model=list[UserTokenResponse])
def list_tokens(
    principal: AuthContext = Depends(require_authenticated_principal),
    db: Session = Depends(get_db),
) -> list[UserTokenResponse]:
    user = _require_user_principal(principal)
    return [serialize_user_token(token) for token in list_user_tokens(db, user=user, include_revoked=True)]


@router.post("/tokens", response_model=UserTokenCreateResponse)
def issue_token(
    payload: UserTokenCreateRequest,
    principal: AuthContext = Depends(require_authenticated_principal),
    db: Session = Depends(get_db),
) -> UserTokenCreateResponse:
    user = _require_user_principal(principal)
    token, raw_token = create_api_token(
        db,
        user=user,
        name=payload.name,
        expires_in_days=payload.expires_in_days,
    )
    db.commit()
    db.refresh(token)
    return serialize_user_token_create(token, raw_token)


@router.delete("/tokens/{token_id}")
def revoke_token(
    token_id: str,
    principal: AuthContext = Depends(require_authenticated_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    token = db.get(UserAPIToken, token_id)
    if not token:
        raise ValueError(f"Token {token_id} not found")
    if not principal.is_admin and principal.user_id != token.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot revoke this token")
    revoke_api_token(token)
    db.commit()
    return {"status": "revoked"}


def _require_user_principal(principal: AuthContext) -> User:
    if principal.user and principal.user.is_active:
        return principal.user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User context required")


def _set_session_cookie(response: Response, *, request: Request, raw_token: str, max_age: int) -> None:
    response.set_cookie(
        WEB_SESSION_COOKIE,
        raw_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=max_age,
    )
