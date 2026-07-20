"""Auth routes: POST /login, GET /me, POST /logout."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Header, Response

from app.auth import service as auth_service
from app.core.deps import ActorDep
from app.core.errors import AuthenticationError
from app.schemas.auth import ActorInfo, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response) -> LoginResponse:
    """Exchange an admin token for a session token."""
    result = await auth_service.login(request.token)
    if result is None:
        raise AuthenticationError("Invalid admin token")
    session_token, actor_id, expires_at = result
    # Set HTTPOnly cookie.
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="strict",
        max_age=7 * 24 * 3600,  # 7 days
    )
    return LoginResponse(
        session_token=session_token,
        actor_id=actor_id,
        auth_method="admin_token",
        expires_at=expires_at,
    )


@router.get("/me", response_model=ActorInfo)
async def me(actor: ActorDep) -> ActorInfo:
    """Return the current authenticated actor."""
    return ActorInfo(actor_id=actor, auth_method="admin_token")


@router.post("/logout")
async def logout(
    actor: ActorDep,
    response: Response,
    session_token: str | None = Cookie(default=None, alias="session_token"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Destroy the current session."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif session_token:
        token = session_token
    if token:
        await auth_service.logout(token)
    response.delete_cookie(key="session_token")
    return {"ok": True}
