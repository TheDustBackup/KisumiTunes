import motor.motor_asyncio
from config import Config

_client = None
_db = None


async def init_db():
    global _client, _db
    _client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGO_URI)
    _db = _client.ambientbot
    # Create index for fast lookups by channel_id
    await _db.channels.create_index('channel_id', unique=True)


async def get_track(channel_id: int) -> str | None:
    doc = await _db.channels.find_one({'channel_id': str(channel_id)})
    return doc['url'] if doc else None


async def set_track(channel_id: int, url: str, guild_id: int):
    await _db.channels.update_one(
        {'channel_id': str(channel_id)},
        {'$set': {
            'channel_id': str(channel_id),
            'guild_id': str(guild_id),
            'url': url,
        }},
        upsert=True,
    )


async def clear_track(channel_id: int):
    await _db.channels.delete_one({'channel_id': str(channel_id)})
