import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "whitelist_helper",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/whitelist.py",
)
wl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wl)


class _Status:
    def __init__(self, name=None, value=None):
        self.name = name
        self.value = value


def test_split_scope_empty():
    assert wl.split_scope([]) == (False, [])


def test_split_scope_global_token():
    assert wl.split_scope(["global", "@user"]) == (True, ["@user"])
    assert wl.split_scope(["toancuc"]) == (True, [])
    is_global, rest = wl.split_scope(["toàncục", "123"])
    assert is_global is True
    assert rest == ["123"]


def test_split_scope_toan_cuc_two_tokens():
    is_global, rest = wl.split_scope(["toàn", "cục", "@nam"])
    assert is_global is True
    assert rest == ["@nam"]
    is_global, rest = wl.split_scope(["toan", "cuc", "1"])
    assert is_global is True
    assert rest == ["1"]


def test_split_scope_regular_user():
    assert wl.split_scope(["@user"]) == (False, ["@user"])
    assert wl.split_scope(["123"]) == (False, ["123"])


def test_is_listed_per_chat_and_global():
    assert wl.is_listed(10, [10, 11], []) is True
    assert wl.is_listed(10, [11], [10]) is True
    assert wl.is_listed(10, [11], [12]) is False
    assert wl.is_listed("10", ["10"], []) is True
    assert wl.is_listed(None, [1], [1]) is False
    assert wl.is_listed("x", [1], [1]) is False


def test_should_auto_restore_unban_and_unrestrict():
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status("BANNED")
    ) == "unban"
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status("RESTRICTED")
    ) == "unrestrict"
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status(value="banned")
    ) == "unban"


def test_should_auto_restore_skips_non_protected_and_bots():
    assert wl.should_auto_restore(
        is_protected=False, user_is_bot=False, new_status=_Status("BANNED")
    ) is None
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=True, new_status=_Status("BANNED")
    ) is None
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status("MEMBER")
    ) is None
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status("LEFT")
    ) is None
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=_Status("ADMINISTRATOR")
    ) is None
    assert wl.should_auto_restore(
        is_protected=True, user_is_bot=False, new_status=None
    ) is None


def test_messages_are_vietnamese_with_diacritics():
    text = wl.protected_html('<a href="tg://user?id=1">Nam</a>')
    assert "danh sách trắng" in text
    assert "mute" in text
    assert "cấm" in text
    assert "Nam" in text
    notice = wl.auto_restore_html("unban", "Nam")
    assert "tự động bỏ cấm" in notice
    notice = wl.auto_restore_html("unrestrict", "Nam")
    assert "tự động gỡ hạn chế" in notice
    miss = wl.missing_rights_html("Nam")
    assert "quyền hạn chế thành viên" in miss


def test_global_chat_id_is_zero():
    assert wl.GLOBAL_CHAT_ID == 0


def test_status_name_fallbacks():
    assert wl.status_name(_Status("restricted")) == "RESTRICTED"
    assert wl.status_name("left") == "LEFT"
    assert wl.status_name(None) == ""
