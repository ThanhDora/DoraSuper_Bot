import re
from logging import getLogger
from typing import Union, List, Any
from pyrogram import Client
from pyrogram.types import Message, InputMedia

LOGGER = getLogger("DoraSuper")

_orig_send_photo = Client.send_photo
_orig_send_video = Client.send_video
_orig_send_document = Client.send_document
_orig_send_media_group = Client.send_media_group

def clean_emoji_html(text: str) -> str:
    if not text:
        return text
    return re.sub(r'<emoji id="[^"]+">(.+?)</emoji>', r'\1', str(text))

def clean_all_html(text: str) -> str:
    if not text:
        return text
    return re.sub(r'<[^>]+>', '', str(text))

async def safe_send_photo(self: Client, chat_id: Union[int, str], photo: Any, caption: str = "", *args, **kwargs) -> Message:
    try:
        return await _orig_send_photo(self, chat_id, photo, caption=caption, *args, **kwargs)
    except Exception as e:
        if "ENTITY_TEXT_INVALID" in str(e):
            LOGGER.warning(f"Failed to send photo due to ENTITY_TEXT_INVALID, applying patch. Chat: {chat_id}")
            try:
                clean_cap = clean_emoji_html(caption)
                return await _orig_send_photo(self, chat_id, photo, caption=clean_cap, *args, **kwargs)
            except Exception:
                try:
                    clean_cap_no_html = clean_all_html(caption)
                    kwargs_copy = kwargs.copy()
                    kwargs_copy["parse_mode"] = None
                    return await _orig_send_photo(self, chat_id, photo, caption=clean_cap_no_html, *args, **kwargs_copy)
                except Exception:
                    raise e
        else:
            raise e

async def safe_send_video(self: Client, chat_id: Union[int, str], video: Any, caption: str = "", *args, **kwargs) -> Message:
    try:
        return await _orig_send_video(self, chat_id, video, caption=caption, *args, **kwargs)
    except Exception as e:
        if "ENTITY_TEXT_INVALID" in str(e):
            LOGGER.warning(f"Failed to send video due to ENTITY_TEXT_INVALID, applying patch. Chat: {chat_id}")
            try:
                clean_cap = clean_emoji_html(caption)
                return await _orig_send_video(self, chat_id, video, caption=clean_cap, *args, **kwargs)
            except Exception:
                try:
                    clean_cap_no_html = clean_all_html(caption)
                    kwargs_copy = kwargs.copy()
                    kwargs_copy["parse_mode"] = None
                    return await _orig_send_video(self, chat_id, video, caption=clean_cap_no_html, *args, **kwargs_copy)
                except Exception:
                    raise e
        else:
            raise e

async def safe_send_document(self: Client, chat_id: Union[int, str], document: Any, caption: str = "", *args, **kwargs) -> Message:
    try:
        return await _orig_send_document(self, chat_id, document, caption=caption, *args, **kwargs)
    except Exception as e:
        if "ENTITY_TEXT_INVALID" in str(e):
            LOGGER.warning(f"Failed to send document due to ENTITY_TEXT_INVALID, applying patch. Chat: {chat_id}")
            try:
                clean_cap = clean_emoji_html(caption)
                return await _orig_send_document(self, chat_id, document, caption=clean_cap, *args, **kwargs)
            except Exception:
                try:
                    clean_cap_no_html = clean_all_html(caption)
                    kwargs_copy = kwargs.copy()
                    kwargs_copy["parse_mode"] = None
                    return await _orig_send_document(self, chat_id, document, caption=clean_cap_no_html, *args, **kwargs_copy)
                except Exception:
                    raise e
        else:
            raise e

async def safe_send_media_group(self: Client, chat_id: Union[int, str], media: List[InputMedia], *args, **kwargs) -> List[Message]:
    try:
        return await _orig_send_media_group(self, chat_id, media, *args, **kwargs)
    except Exception as e:
        if "ENTITY_TEXT_INVALID" in str(e):
            LOGGER.warning(f"Failed to send media group due to ENTITY_TEXT_INVALID, applying patch. Chat: {chat_id}")
            try:
                for item in media:
                    if getattr(item, "caption", None):
                        item.caption = clean_emoji_html(item.caption)
                return await _orig_send_media_group(self, chat_id, media, *args, **kwargs)
            except Exception:
                try:
                    for item in media:
                        if getattr(item, "caption", None):
                            item.caption = clean_all_html(item.caption)
                            item.parse_mode = None
                    return await _orig_send_media_group(self, chat_id, media, *args, **kwargs)
                except Exception:
                    raise e
        else:
            raise e

Client.send_photo = safe_send_photo
Client.send_video = safe_send_video
Client.send_document = safe_send_document
Client.send_media_group = safe_send_media_group
