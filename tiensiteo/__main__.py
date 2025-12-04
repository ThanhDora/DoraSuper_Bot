import asyncio
import importlib
import os
import pickle
import logging
import traceback
from logging import getLogger

from pyrogram import __version__, idle
from pyrogram.raw.all import layer

from database import dbname
from tiensiteo import (
    BOT_NAME,
    BOT_USERNAME,
    HELPABLE,
    UBOT_NAME,
    app,
    get_event_loop,
    scheduler,
)
from tiensiteo.plugins import ALL_MODULES
from tiensiteo.vars import SUDO, USER_SESSION
from utils import auto_clean

LOGGER = getLogger("TienSiTeo")
# Run Bot
async def start_bot():
    try:
        for module in ALL_MODULES:
            try:
                imported_module = importlib.import_module(f"tiensiteo.plugins.{module}")
                if hasattr(imported_module, "__MODULE__") and imported_module.__MODULE__:
                    imported_module.__MODULE__ = imported_module.__MODULE__
                    if hasattr(imported_module, "__HELP__") and imported_module.__HELP__:
                        HELPABLE[imported_module.__MODULE__.lower()] = imported_module
            except Exception as e:
                LOGGER.error(f"Failed to load module {module}: {str(e)}")

        bot_modules = ""
        j = 1
        for i in ALL_MODULES:
            if j == 4:
                bot_modules += "|{:<15}|\n".format(i)
                j = 0
            else:
                bot_modules += "|{:<15}".format(i)
            j += 1
        LOGGER.info("+===============================================================+")
        LOGGER.info("|                        TienSiTeo                           |")
        LOGGER.info("+===============+===============+===============+===============+")
        LOGGER.info(bot_modules)
        LOGGER.info("+===============+===============+===============+===============+")
        LOGGER.info("[INFO]: BOT STARTED AS @%s!", BOT_USERNAME)

        LOGGER.info("[INFO]: SENDING ONLINE STATUS")
        for i in SUDO:
            try:
                if USER_SESSION:
                    await app.send_message(
                        i,
                        f"<b>Bot và UserBot đã khởi động thành công</b>\n\nUserBot: {UBOT_NAME} và Bot: {BOT_NAME}\n\nBot sử dụng Pyrogram v{__version__} (Layer {layer}) và đã khởi động như @{BOT_USERNAME}.\n\n<blockquote expandable>{bot_modules}</blockquote>",
                    )
                else:
                    await app.send_message(
                        i,
                        f"<b>Bot đã khởi động thành công với tên {BOT_NAME}</b>\n\nBot sử dụng Pyrogram v{__version__} (Layer {layer}) và đã khởi động như @{BOT_USERNAME}.\n\n<blockquote expandable>{bot_modules}</blockquote>",
                    )
            except Exception as e:
                LOGGER.error(f"Failed to send message to {i}: {str(e)}")

        try:
            scheduler.start()
        except Exception as e:
            LOGGER.error(f"Failed to start scheduler: {str(e)}")

        if os.path.exists("restart.pickle"):
            try:
                with open("restart.pickle", "rb") as status:
                    chat_id, message_id = pickle.load(status)
                os.remove("restart.pickle")
                await app.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="<b>Tiến sĩ Tèo đã khởi động lại thành công!</b>",
                )
            except Exception as e:
                LOGGER.error(f"Failed to handle restart.pickle: {str(e)}")

        try:
            asyncio.create_task(auto_clean())
        except Exception as e:
            LOGGER.error(f"Failed to start auto_clean task: {str(e)}")

        await idle()
    except Exception as e:
        LOGGER.error(f"Error in start_bot: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        get_event_loop().run_until_complete(start_bot())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped by user")
    except Exception:
        err = traceback.format_exc()
        LOGGER.error(f"Error occurred: {err}")
    finally:
        LOGGER.info("------------------------ Stopped Services ------------------------")