import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID


class AlarmBroker:
    """Process-local fan-out for alarm transitions received by this API worker."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[dict[str, object]]]] = (
            defaultdict(set)
        )
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(self, user_id: UUID) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=16)
        async with self._lock:
            self._subscribers[user_id].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(user_id)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(user_id, None)

    async def publish(self, user_id: UUID, message: dict[str, object]) -> None:
        async with self._lock:
            queues = tuple(self._subscribers.get(user_id, ()))
        for queue in queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(message)


alarm_broker = AlarmBroker()

__all__ = ["AlarmBroker", "alarm_broker"]
