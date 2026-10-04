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


# ---------------------------------------------------------------- F50 name search
_WORD = re.compile(r"[a-z0-9]+")
_LINKING = {"na", "do", "we", "ze", "im", "przy", "pod", "nad", "od", "obok"}  # "teatr na Słowackiego"


def fold(value: str) -> str:
    """Lower case without Polish (and other) diacritics: 'Pływalnia Śląska' → 'plywalnia slaska'."""
    import unicodedata

    text = value.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _stem(token: str) -> str:
    """Drop an inflection ending: 'teatru' → 'teat', 'slowackiego' → 'slowacki' (short words stay whole)."""
    return token if len(token) <= 4 else token[:max(4, len(token) - 3)]


def name_matches(query: str, name: str) -> bool:
    """Every query word starts a word of the name (diacritics and Polish endings ignored), or the folded query
    is a plain fragment of the folded name. 'Teatru Słowackiego' finds 'Teatr im. Juliusza Słowackiego'."""
    q, n = fold(query).strip(), fold(name)
    if not q:
        return True
    if q in n:
        return True
    words = _WORD.findall(n)
    tokens = [t for t in _WORD.findall(q) if len(t) > 1 and t not in _LINKING]
    return bool(tokens) and all(any(w.startswith(_stem(t)) for w in words) for t in tokens)


_STREET_WORDS = {"ulicy", "ulica", "ul", "ul.", "alei", "al", "al."}


def _nominative_word(word: str) -> str:
    lower = word.lower()
    if len(word) <= 4 or any(c.isdigit() for c in word):
        return word
    for ending, replacement in (("iej", "a"), ("ego", "e"), ("ii", "ia"), ("y", "a"), ("u", "")):
        if lower.endswith(ending):
            return word[: len(word) - len(ending)] + replacement
    return word


def nominative(query: str) -> str:
    """Rough nominative of a Polish place phrase for the geocoder (Nominatim does not decline):
    'Tauron Areny' → 'Tauron Arena', 'ulicy Lea 120' → 'Lea 120', 'Teatru Bagatela' → 'Teatr Bagatela'."""
    words = [w for w in query.split() if w.lower() not in _STREET_WORDS]
    return " ".join(_nominative_word(w) for w in words)
