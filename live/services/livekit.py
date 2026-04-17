# live/services/livekit.py

import asyncio
from datetime import timedelta
from livekit import api
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def get_livekit_token(room_name: str, identity: str, name: str = None, ttl_seconds: int = 86400) -> str:
    """Generate an access token for a LiveKit room."""
    # Convert TTL from seconds to a timedelta object
    ttl_delta = timedelta(seconds=ttl_seconds)

    token = (api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
             .with_identity(identity)
             .with_name(name or identity)
             .with_ttl(ttl_delta)  # <-- Pass the timedelta object here
             .with_grants(api.VideoGrants(
                 room_join=True,
                 room=room_name,
             )))
    return token.to_jwt()

def _run_async(coro):
    """Safely run an async function, handling existing event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Walang running loop, pwedeng gumamit ng asyncio.run()
        return asyncio.run(coro)
    else:
        # May existing loop (e.g., sa ASGI), gumamit ng run_coroutine_threadsafe
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

async def _create_room_async(room_name: str, empty_timeout: int, max_participants: int) -> bool:
    async with api.LiveKitAPI(settings.LIVEKIT_URL) as lkapi:
        try:
            rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
            for room in rooms.rooms:
                if room.name == room_name:
                    logger.info(f"Room {room_name} already exists.")
                    return True

            await lkapi.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=empty_timeout,
                    max_participants=max_participants,
                )
            )
            logger.info(f"Created LiveKit room: {room_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create room {room_name}: {e}")
            return False

def create_livekit_room(room_name: str, empty_timeout: int = 60, max_participants: int = 0) -> bool:
    """Synchronous wrapper to create a room."""
    return _run_async(_create_room_async(room_name, empty_timeout, max_participants))

async def _delete_room_async(room_name: str) -> bool:
    async with api.LiveKitAPI(settings.LIVEKIT_URL) as lkapi:
        try:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"Deleted LiveKit room: {room_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete room {room_name}: {e}")
            return False

def delete_livekit_room(room_name: str) -> bool:
    return _run_async(_delete_room_async(room_name))

async def _is_room_active_async(room_name: str) -> bool:
    async with api.LiveKitAPI(settings.LIVEKIT_URL) as lkapi:
        rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
        for room in rooms.rooms:
            if room.name == room_name:
                return True
        return False

def is_room_active(room_name: str) -> bool:
    return _run_async(_is_room_active_async(room_name))