import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.queue import get_arq_pool
from app.core.security import decode_access_token
from app.models.user import User

# 关闭 HTTPBearer 默认的缺凭证自动报错（默认 403 且英文 detail），
# 改由本模块统一抛 401，前端只需识别一种未登录状态。
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_queue() -> ArqRedis:
    return await get_arq_pool()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise _unauthorized()

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise _unauthorized()

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise _unauthorized() from None

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _unauthorized()
    return user
