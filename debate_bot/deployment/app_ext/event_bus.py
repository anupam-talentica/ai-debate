import json
import logging
import os
from typing import AsyncGenerator, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_redis_client: Optional[redis.Redis] = None


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _channel(run_id: str) -> str:
    return f"debate:{run_id}"


async def publish(run_id: str, event: dict) -> None:
    """Publish a debate event to the run's Redis pub/sub channel."""
    await _client().publish(_channel(run_id), json.dumps(event))


async def open_subscription(run_id: str) -> redis.client.PubSub:
    """Subscribe to a run's Redis channel and return the subscribed PubSub.

    Split out from `subscribe()` so a caller can subscribe *before* deciding
    whether to claim/execute the run — subscribing first means no event
    published after this call is ever missed, regardless of that decision.
    """
    pubsub = _client().pubsub()
    channel = _channel(run_id)
    await pubsub.subscribe(channel)
    logger.info(f"subscribed to {channel}")
    return pubsub


async def listen(pubsub: redis.client.PubSub, poll_timeout: Optional[float] = None) -> AsyncGenerator[Optional[dict], None]:
    """Yield decoded events as they arrive on an already-subscribed PubSub.

    Without `poll_timeout`, blocks indefinitely between messages (the plain
    relay case). With `poll_timeout` set, yields None after that many seconds
    without a message instead of blocking forever — lets a caller interleave
    periodic work (e.g. re-checking run ownership) between messages without
    missing any.
    """
    if poll_timeout is None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield json.loads(message["data"])
        return

    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_timeout)
        if message is None:
            yield None
            continue
        yield json.loads(message["data"])


async def close_subscription(pubsub: redis.client.PubSub) -> None:
    """Unsubscribe and release a PubSub opened by open_subscription()."""
    await pubsub.aclose()


async def subscribe(run_id: str) -> AsyncGenerator[dict, None]:
    """Subscribe to a run's Redis channel and yield decoded events as they arrive.

    Pub/sub has no history — a subscriber only sees events published after it
    subscribes, not anything that fired before.
    """
    pubsub = await open_subscription(run_id)
    try:
        async for event in listen(pubsub):
            yield event
    finally:
        await close_subscription(pubsub)


async def close() -> None:
    """Release the shared Redis connection. Call once at process shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
