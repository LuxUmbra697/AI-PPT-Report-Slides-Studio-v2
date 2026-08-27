from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.security import (
    create_access_token,
    dummy_password_hash,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _normalize_email(email: str) -> str:
    # 统一小写并去空白，避免同一邮箱因大小写不同被重复注册
    return email.strip().lower()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        token_type="bearer",
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(body: RegisterRequest, session: SessionDep) -> TokenResponse:
    email = _normalize_email(str(body.email))

    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被注册",
        )

    user = User(email=email, password_hash=hash_password(body.password))
    session.add(user)
    try:
        # 唯一约束兜底：并发下先查后插仍可能撞车
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被注册",
        ) from None

    await session.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    email = _normalize_email(str(body.email))
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # 用户不存在时也对固定假哈希做一次 verify，消除时序侧信道
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    if not verify_password(body.password, password_hash) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    return _token_response(user)


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUser) -> User:
    return current_user
