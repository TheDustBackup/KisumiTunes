import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    MONGO_URI     = os.getenv('MONGO_URI')
    YTDLP_COOKIES = os.getenv('YTDLP_COOKIES')  # optional path to a Netscape cookies.txt
