import os
import time
import asyncio
import uvloop

uvloop.install()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from faulthandler import enable as faulthandler_enable
from logging import ERROR, INFO, StreamHandler, basicConfig, getLogger, handlers

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from async_pymongo import AsyncClient
from pymongo import MongoClient
from pyrogram import Client

from dorasuper.vars import (
    API_HASH,
    API_ID,
    BOT_TOKEN,
    DATABASE_NAME,
    DATABASE_URI,
    TZ,
    USER_SESSION,
)

basicConfig(
    level=INFO,
    format="[%(levelname)s] - [%(asctime)s - %(name)s - %(message)s] -> [%(module)s:%(lineno)d]",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        handlers.RotatingFileHandler(
            "DoraLogs.txt", mode="a", encoding="utf-8", maxBytes=5242880, backupCount=1
        ),
        StreamHandler(),
    ],
)
getLogger("pyrogram").setLevel(ERROR)
getLogger("httpx").setLevel(ERROR)

MOD_LOAD = []
MOD_NOLOAD = []
HELPABLE = {}
cleanmode = {}
botStartTime = time.time()
dorasuper_version = "v3.0"

faulthandler_enable()
from dorasuper.core import dorasuper_patch

# Pyrogram Bot Client
app = Client(
    "DoraSuperBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    mongodb=dict(connection=AsyncClient(DATABASE_URI), remove_peers=True),
    sleep_threshold=180,
    app_version="3.0",
    workers=50,
    max_concurrent_transmissions=4
)
app.db = AsyncClient(DATABASE_URI)
app.log = getLogger("DoraSuper")

# Pyrogram UserBot Client
user = Client(
    "DoraSuperUbot",
    session_string=USER_SESSION,
    mongodb=dict(connection=AsyncClient(DATABASE_URI), remove_peers=False),
    sleep_threshold=180,
    app_version="1.0"
)

jobstores = {
    "default": MongoDBJobStore(
        client=MongoClient(DATABASE_URI), database=DATABASE_NAME, collection="nightmode"
    )
}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=TZ)

app.start()
BOT_ID = app.me.id
BOT_NAME = app.me.first_name
BOT_USERNAME = app.me.username
if USER_SESSION:
    user.start()
    UBOT_ID = user.me.id
    UBOT_NAME = user.me.first_name
    UBOT_USERNAME = user.me.username
else:
    UBOT_ID = None
    UBOT_NAME = None
    UBOT_USERNAME = None
