import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "autodel",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/autodel.py",
)
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)


class _Msg:
    def __init__(self, text=None, caption=None, **media):
        self.text = text
        self.caption = caption
        self.photo = media.get("photo")
        self.video = media.get("video")
        self.document = media.get("document")
        self.audio = media.get("audio")
        self.animation = media.get("animation")
        self.voice = media.get("voice")
        self.video_note = media.get("video_note")
        self.sticker = media.get("sticker")
        self.media_group_id = media.get("media_group_id")


def test_is_command_text():
    assert ad.is_command_text("/up")
    assert ad.is_command_text("!ping")
    assert not ad.is_command_text("hello")
    assert not ad.is_command_text("")


def test_clamp_seconds():
    assert ad.clamp_seconds(60) == 60
    assert ad.clamp_seconds(1) == 5
    assert ad.clamp_seconds(999999) == 86400


def test_should_autodel_text_reply():
    msg = _Msg(text="ok")
    assert ad.should_autodel_bot_message(msg, in_command=True) is True
    assert ad.should_autodel_bot_message(msg, in_command=False) is False
    assert ad.should_autodel_bot_message(msg, in_command=True, exclude=True) is False


def test_should_keep_media():
    assert ad.should_autodel_bot_message(_Msg(document=object(), caption="x"), in_command=True) is False
    assert ad.should_autodel_bot_message(_Msg(photo=object()), in_command=True) is False
    assert ad.should_autodel_bot_message(_Msg(video=object()), in_command=True) is False
    assert ad.should_autodel_bot_message(_Msg(audio=object()), in_command=True) is False


def test_skip_autodel_context():
    assert ad.in_command_context() is False
    ad.mark_command_context()
    assert ad.in_command_context() is True
    with ad.skip_autodel():
        # exclude flag on; decision helper uses exclude arg separately
        pass
    ad.clear_command_context()
    assert ad.in_command_context() is False
