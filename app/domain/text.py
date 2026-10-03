"""F42 user-text hygiene. Pure. Plain text only: HTML tags, angle brackets and control characters are removed
(newlines and tabs kept). Defence in depth — clients must still render user text as text, never as HTML."""
import re

_TAG = re.compile(r"<[^<>]*>")
_ANGLE = re.compile(r"[<>]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
_PHONE = re.compile(r"[0-9+()\-\s]{3,30}")


def clean_text(value: str) -> str:
    text = _TAG.sub("", value)          # <script>, <img …>, <b> …
    text = _ANGLE.sub("", text)         # leftovers / unclosed tags
    return _CONTROL.sub("", text)


def is_http_url(value: str) -> bool:
    return bool(_URL.fullmatch(value.strip()))


def is_email(value: str) -> bool:
    return bool(_EMAIL.fullmatch(value.strip()))


def is_phone(value: str) -> bool:
    return bool(_PHONE.fullmatch(value.strip()))
