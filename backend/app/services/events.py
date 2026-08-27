import uuid

from pydantic import BaseModel

from app.core.redis import get_redis

SNAPSHOT_TTL_SECONDS = 60 * 60


class EventStream[EventT: BaseModel]:
    """基于 Redis 发布订阅的进度通道。

    发布时同时写一份最近快照：SSE 断线重连后不必等下一条消息才能
    恢复当前状态，否则任务安静的那段时间里前端会一直空着。
    """

    def __init__(self, name: str, event_type: type[EventT]) -> None:
        self._name = name
        self._event_type = event_type

    def channel(self, key: uuid.UUID) -> str:
        return f"{self._name}:{key}:events"

    def _snapshot_key(self, key: uuid.UUID) -> str:
        return f"{self._name}:{key}:snapshot"

    async def publish(self, key: uuid.UUID, event: EventT) -> None:
        redis = get_redis()
        payload = event.model_dump_json()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(self._snapshot_key(key), payload, ex=SNAPSHOT_TTL_SECONDS)
            pipe.publish(self.channel(key), payload)
            await pipe.execute()

    async def latest(self, key: uuid.UUID) -> EventT | None:
        payload = await get_redis().get(self._snapshot_key(key))
        if payload is None:
            return None
        return self._event_type.model_validate_json(payload)

    async def clear(self, key: uuid.UUID) -> None:
        await get_redis().delete(self._snapshot_key(key))
