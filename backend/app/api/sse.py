import asyncio
import uuid
from collections.abc import AsyncGenerator
from collections.abc import Set as AbstractSet

from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.redis import get_redis
from app.services.events import EventStream

HEARTBEAT_TIMEOUT_SECONDS = 15


def event_stream_response(
    request: Request,
    *,
    stream: EventStream,
    key: uuid.UUID,
    fallback: BaseModel,
    terminal_types: AbstractSet[str],
) -> StreamingResponse:
    """把一条 Redis 事件通道包装成 SSE 响应。

    首帧总是先发一次当前状态：客户端可能在任务安静期才连上来，
    只转发后续消息会让界面长时间空白。
    """
    channel = stream.channel(key)

    async def events() -> AsyncGenerator[str, None]:
        initial = await stream.latest(key) or fallback
        yield _encode(initial)

        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel)
        try:
            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=HEARTBEAT_TIMEOUT_SECONDS,
                )
                if message is None:
                    # 心跳注释帧：让中间代理不要把空闲连接当成僵死连接掐掉
                    yield ": heartbeat\n\n"
                    continue

                event = type(fallback).model_validate_json(message["data"])
                yield _encode(event)
                if getattr(event, "type", None) in terminal_types:
                    return
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _encode(event: BaseModel) -> str:
    return f"event: {getattr(event, 'type', 'message')}\ndata: {event.model_dump_json()}\n\n"
