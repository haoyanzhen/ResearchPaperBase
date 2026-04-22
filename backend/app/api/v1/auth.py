from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, revoke_token
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    UpdateMeRequest,
    UserInfo,
)
from app.schemas.common import ok
from app.services import auth_service
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await auth_service.username_exists(db, body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    if await auth_service.email_exists(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "邮箱已注册")

    user = await auth_service.create_user(db, body.username, body.email, body.password)
    return ok(RegisterResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    ))


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, body.credential, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名/邮箱或密码错误")

    token = create_access_token(user.id)
    return ok(LoginResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserInfo(user_id=user.id, username=user.username, email=user.email,
                      is_admin=user.is_admin),
    ))


@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    revoke_token(token)
    return ok({"message": "logged out"})


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return ok(MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    ))


@router.patch("/me")
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username and body.username != current_user.username:
        if await auth_service.username_exists(db, body.username):
            raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    if body.email and body.email != current_user.email:
        if await auth_service.email_exists(db, body.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "邮箱已注册")

    user = await auth_service.update_user(db, current_user, body.username, body.email, body.password)
    return ok(MeResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
    ))
