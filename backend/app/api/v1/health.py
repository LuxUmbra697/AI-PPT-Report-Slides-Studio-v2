from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.db import async_session_factory
from app.core.redis import get_redis

router = APIRouter(tags=["health"])

ComponentState = Literal["ok", "down"]


class HealthResponse(BaseModel):
    """显式声明响应模型，让 OpenAPI 产出带字段的 schema。
    前端类型由 OpenAPI 生成，接口若只返回裸 dict，生成结果会退化为 object。"""

    status: Literal["ok"]
    database: ComponentState
    redis: ComponentState


async def _probe_database() -> ComponentState:
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return "down"
    return "ok"


async def _probe_redis() -> ComponentState:
    try:
        return "ok" if await get_redis().ping() else "down"
    except Exception:
        return "down"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # 依赖不可达时接口本身仍算成功，由字段区分，
    # 否则前端无法区分"服务挂了"和"服务在但数据库没起"。
    return HealthResponse(
        status="ok",
        database=await _probe_database(),
        redis=await _probe_redis(),
    )
