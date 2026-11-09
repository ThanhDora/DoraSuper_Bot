"""Offline tests for admin log media vs command routing helpers."""
import ast
import os
import types
import unittest
from pathlib import Path

os.environ["DORASUPER_OFFLINE"] = "1"

# Stub heavy imports so we can exec helper functions without loading pyrogram app / Mongo.
_src_path = Path(__file__).resolve().parents[1] / "dorasuper/plugins/admin_log_messages.py"
_src = _src_path.read_text(encoding="utf-8")

# Ensure icon-only text stand-ins are not assigned as content
assert 'content = "📷 Ảnh"' not in _src
assert 'content = "🎬 Video"' not in _src


class _FakePhoto:
    file_id = "photo-file-id"


class _FakeVideo:
    file_id = "video-file-id"


class _FakeVideoNote:
    file_id = "vnote-file-id"


class _FakeDocument:
    file_id = "doc-file-id"
    file_name = "app.ipa"


class _FakeAudio:
    file_id = "audio-file-id"


class _FakeVoice:
    file_id = "voice-file-id"


class _FakeSticker:
    file_id = "sticker-file-id"


class _FakeUser:
    def __init__(self, first_name="A", last_name="", username=None, uid=1, is_bot=False):
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.id = uid
        self.is_bot = is_bot


class _FakeChat:
    def __init__(self, type_, title=None, cid=-1001):
        self.type = type_
        self.title = title
        self.id = cid


class _FakeMessage:
    def __init__(
        self,
        *,
        text=None,
        caption=None,
        photo=None,
        video=None,
        video_note=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        sticker=None,
        chat=None,
        from_user=None,
    ):
        self.text = text
        self.caption = caption
        self.photo = photo
        self.video = video
        self.video_note = video_note
        self.document = document
        self.audio = audio
        self.voice = voice
        self.animation = animation
        self.sticker = sticker
        self.chat = chat
        self.from_user = from_user


# Load only pure helpers via AST (skip decorator handler and imports that need live app)
_tree = ast.parse(_src)
_keep_names = {
    "_is_command_message",
    "_is_media_message",
    "_is_file_message",
    "_has_copyable_payload",
    "_media_topic_key",
    "_build_user_chat_caption",
    "_build_text_log_body",
}
_body = []
for node in _tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in _keep_names:
        _body.append(node)

# Minimal stubs for names used by _build_user_chat_caption
class _ChatType:
    GROUP = "group"
    SUPERGROUP = "supergroup"
    PRIVATE = "private"


mod = types.ModuleType("admin_log_helpers")
ns = {
    "html": __import__("html"),
    "ChatType": _ChatType,
    "E_USER": '<tg-emoji emoji-id="1">👤</tg-emoji>',
    "E_MSG": '<tg-emoji emoji-id="2">💬</tg-emoji>',
    "COMMAND_HANDLER": ("/", "!"),
}
exec(compile(ast.Module(body=_body, type_ignores=[]), "admin_log_helpers", "exec"), ns)
for k, v in ns.items():
    if not k.startswith("__"):
        setattr(mod, k, v)


class AdminLogHelpersTest(unittest.TestCase):
    def test_command_detection(self):
        self.assertTrue(mod._is_command_message("/ping"))
        self.assertTrue(mod._is_command_message("!help me"))
        self.assertFalse(mod._is_command_message("hello"))
        self.assertFalse(mod._is_command_message("/"))
        self.assertFalse(mod._is_command_message(""))

    def test_media_detection_and_topic(self):
        pm = _FakeMessage(photo=_FakePhoto(), chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertTrue(mod._is_media_message(pm))
        self.assertEqual(mod._media_topic_key(pm), "photos")

        vid = _FakeMessage(video=_FakeVideo(), chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertTrue(mod._is_media_message(vid))
        self.assertEqual(mod._media_topic_key(vid), "videos")

        note = _FakeMessage(video_note=_FakeVideoNote(), chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertTrue(mod._is_media_message(note))
        self.assertEqual(mod._media_topic_key(note), "videos")

        plain = _FakeMessage(text="/start", chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertFalse(mod._is_media_message(plain))

    def test_pm_media_is_not_icon_text_path(self):
        """Regression: PM photo/video must be classified as media (not icon-only text)."""
        pm_photo = _FakeMessage(
            photo=_FakePhoto(),
            caption="hi",
            chat=_FakeChat(_ChatType.PRIVATE, cid=123),
            from_user=_FakeUser(first_name="Bob", username="bob", uid=42),
        )
        self.assertTrue(mod._is_media_message(pm_photo))
        # Media path takes priority over command path even if caption looks like a command
        pm_cmd_cap = _FakeMessage(
            photo=_FakePhoto(),
            caption="/start",
            chat=_FakeChat(_ChatType.PRIVATE),
            from_user=_FakeUser(),
        )
        self.assertTrue(mod._is_media_message(pm_cmd_cap))
        self.assertTrue(mod._is_command_message(pm_cmd_cap.caption))

    def test_caption_keeps_tg_emoji_and_user_chat(self):
        msg = _FakeMessage(
            photo=_FakePhoto(),
            caption="hello <world>",
            chat=_FakeChat(_ChatType.SUPERGROUP, title="Test Group", cid=-10099),
            from_user=_FakeUser(first_name="Ann", username="ann", uid=7),
        )
        cap = mod._build_user_chat_caption(msg, msg.caption)
        self.assertIn("tg-emoji", cap)
        self.assertIn("Ann", cap)
        self.assertIn("@ann", cap)
        self.assertIn("Test Group", cap)
        self.assertIn("hello &lt;world&gt;", cap)
        self.assertLessEqual(len(cap), 1024)


    def test_file_detection(self):
        doc = _FakeMessage(document=_FakeDocument(), chat=_FakeChat(_ChatType.SUPERGROUP, title="G"), from_user=_FakeUser())
        self.assertTrue(mod._is_file_message(doc))
        self.assertFalse(mod._is_media_message(doc))
        self.assertTrue(mod._has_copyable_payload(doc))

        audio = _FakeMessage(audio=_FakeAudio(), chat=_FakeChat(_ChatType.SUPERGROUP), from_user=_FakeUser())
        self.assertTrue(mod._is_file_message(audio))

        voice = _FakeMessage(voice=_FakeVoice(), chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertTrue(mod._is_file_message(voice))

        sticker = _FakeMessage(sticker=_FakeSticker(), chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertFalse(mod._is_file_message(sticker))
        self.assertTrue(mod._has_copyable_payload(sticker))

        plain = _FakeMessage(text="hi", chat=_FakeChat(_ChatType.PRIVATE), from_user=_FakeUser())
        self.assertFalse(mod._is_file_message(plain))
        self.assertFalse(mod._has_copyable_payload(plain))

    def test_text_log_body_pm_and_group(self):
        pm = _FakeMessage(
            text="xin chào <b>",
            chat=_FakeChat(_ChatType.PRIVATE, cid=9),
            from_user=_FakeUser(first_name="Lan", username="lan", uid=5),
        )
        body = mod._build_text_log_body(pm, pm.text)
        self.assertIn("Riêng tư (PM)", body)
        self.assertIn("Lan", body)
        self.assertIn("xin chào &lt;b&gt;", body)

        grp = _FakeMessage(
            text="file note",
            chat=_FakeChat(_ChatType.SUPERGROUP, title="Dev", cid=-1001),
            from_user=_FakeUser(first_name="Nam", uid=8),
        )
        body2 = mod._build_text_log_body(grp, grp.text)
        self.assertIn("Dev", body2)
        self.assertIn("-1001", body2)

    def test_source_routes_pm_and_files(self):
        self.assertIn('"pm"', _src)
        self.assertIn('"files"', _src)
        self.assertIn("_is_file_message", _src)
        self.assertIn("_send_payload_to_topic", _src)
        self.assertIn("UP_CHANNEL", _src)

    def test_source_has_no_icon_only_standins(self):
        self.assertNotIn('content = "📷 Ảnh"', _src)
        self.assertNotIn('content = "🎬 Video"', _src)
        self.assertIn("_send_media_to_log", _src)
        self.assertIn("send_document", _src)
        self.assertIn("FloodWait", _src)
        self.assertIn("send_photo", _src)
        self.assertIn("send_video", _src)
        self.assertIn("Forbidden", _src)


if __name__ == "__main__":
    unittest.main()
