import uuid

from app.schemas.outline import OutlineEvent
from app.services.events import EventStream

outline_events: EventStream[OutlineEvent] = EventStream("outline", OutlineEvent)


async def publish_outline_event(project_id: uuid.UUID, event: OutlineEvent) -> None:
    await outline_events.publish(project_id, event)
