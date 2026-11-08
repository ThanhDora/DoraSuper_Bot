"""Khớp từ khóa tăng/giảm điểm Fame, không phụ thuộc Telegram."""
import html
import re

_UPVOTE_WORDS = r"like|thank you|thanks|thank|cảm ơn|cám ơn|c\.ơn|đội ơn|tks"
_DOWNVOTE_WORDS = r"không thích|unlike|dislike"

REGEX_UPVOTE = re.compile(
    rf"(?:(?i:\b(?:{_UPVOTE_WORDS})\b)|👍|(?<!\S)(?:\+{{1,2}}|\+1)(?!\S))"
)
REGEX_DOWNVOTE = re.compile(
    rf"(?:(?i:\b(?:{_DOWNVOTE_WORDS})\b)|👎|(?<!\S)(?:-{{1,2}}|-1)(?!\S))"
)


def is_upvote(text: str) -> bool:
    text = (text or "").strip()
    return bool(text and REGEX_UPVOTE.search(text))


def is_downvote(text: str) -> bool:
    text = (text or "").strip()
    return bool(text and REGEX_DOWNVOTE.search(text))


def mention_html(user_id: int, name: str) -> str:
    safe = html.escape(str(name or "Thành viên"))
    return f'<a href="tg://user?id={int(user_id)}">{safe}</a>'


def mention_user(user) -> str:
    name = getattr(user, "first_name", None) or "Thành viên"
    return mention_html(user.id, name)
