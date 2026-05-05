import base64
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()


def _resolve_cookies() -> str | None:
    # Option A: direct path to a cookies.txt file (local dev)
    path = os.getenv('YTDLP_COOKIES')
    if path:
        return path
    # Option B: base64-encoded cookies string (Railway / env-only deployments)
    b64 = os.getenv('YTDLP_COOKIES_B64')
    if b64:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb')
        tmp.write(base64.b64decode(b64))
        tmp.close()
        return tmp.name
    return None


class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    MONGO_URI     = os.getenv('MONGO_URI')
    YTDLP_COOKIES = _resolve_cookies()
