"""What a name, a key, and a property may hold. Checked before anything reaches FalkorDB.

The limits bound the work one call can cause. FalkorDB runs one write at a time per graph
and cannot stop a write that takes too long, so no input may be able to make one.
"""

import math
import re
import reprlib
import unicodedata

from lighthouse.kinds import NAME

MAX_NAME = 200  # characters in a key, an id, or a name
MAX_TEXT = 100_000  # characters in one text value
MAX_ITEMS = 1_000  # items in one list value
MAX_VALUES = 200  # properties in one row or entry
MAX_REFERENCES = 200  # targets of one relation; references of one entry or episode
MAX_SIZE = 200_000  # characters of one row or entry as a whole
MAX_DETAIL = 2_000  # characters kept of a refused write

# The searchable text of a node: its words only, one space between them. The full-text
# index reads this property and no other. FalkorDB's index does not split words at a line
# break, a no-break space, or an underscore, so the text is never indexed as it is.
WORDS = "words"
WORD = re.compile(r"[^\W_]+")

_SHORT = reprlib.Repr()
_SHORT.maxlevel = 3
_SHORT.maxdict = _SHORT.maxlist = _SHORT.maxtuple = _SHORT.maxset = 20
_SHORT.maxstring = _SHORT.maxother = 200


def describe(thing) -> str:
    """Any value as short text. Safe for a value that is deep, cyclic, or huge."""
    return _SHORT.repr(thing)


def is_name(value) -> bool:
    """Text that identifies something: 1 to 200 characters, all visible, no space at either
    end. Control characters, invisible format characters, and line breaks are refused, so
    two names that look the same on screen are the same text more often."""
    if not isinstance(value, str) or not 0 < len(value) <= MAX_NAME or value != value.strip():
        return False
    categories = {unicodedata.category(character) for character in value}
    return not any(category[0] == "C" or category in ("Zl", "Zp") for category in categories)


def named(**names) -> None:
    """Each argument must be a name. Raises ValueError otherwise."""
    for what, value in names.items():
        if not is_name(value):
            raise ValueError(f"{what} must be text of 1 to {MAX_NAME} visible characters")


def whole_number(value, what: str, most: int) -> int:
    """A count or a limit that a caller gives: a whole number from 1 to `most`."""
    if type(value) is not int or not 1 <= value <= most:
        raise ValueError(f"{what} must be a whole number from 1 to {most}")
    return value


def _is_integer(value) -> bool:
    return type(value) is int and -(2**63) <= value < 2**63


def is_key(value) -> bool:
    """A key is a name, or an integer that fits in 64 bits."""
    return is_name(value) or _is_integer(value)


def _can_be_sent(text: str) -> bool:
    """FalkorDB cannot take a NUL in text, and a lone surrogate cannot be encoded."""
    if "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def is_storable(value, in_list: bool = False) -> bool:
    """What FalkorDB keeps as a property: text, numbers, booleans, and flat lists of them,
    within the size limits."""
    if isinstance(value, list) and not in_list:
        return len(value) <= MAX_ITEMS and all(
            v is not None and is_storable(v, in_list=True) for v in value
        )
    if isinstance(value, str):
        return len(value) <= MAX_TEXT and _can_be_sent(value)
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, bool) or _is_integer(value)


def mapping(value, what: str) -> dict:
    """An optional map. Missing or null is empty; any other type is an error."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{what} must be a map")
    return value


def properties(given, forbidden: set[str], what: str) -> dict:
    """A property map, checked. Null means absent, so nulls are dropped."""
    given = mapping(given, what)
    if len(given) > MAX_VALUES:
        raise ValueError(f"{what}: more than {MAX_VALUES} properties")
    checked = {}
    for name, value in given.items():
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(f"{what}: invalid property name {describe(name)}")
        if name in forbidden:
            raise ValueError(f"{what}: {name!r} is a name the library uses")
        if not is_storable(value):
            raise ValueError(f"{what}.{name}: value cannot be stored: {describe(value)}")
        if value is not None:
            checked[name] = value
    return checked


def references(keys, what: str) -> list:
    """Keys that point at entities: checked, without doubles, in a fixed order."""
    keys = [] if keys is None else keys if isinstance(keys, (list, tuple)) else [keys]
    if len(keys) > MAX_REFERENCES:
        raise ValueError(f"{what}: more than {MAX_REFERENCES} references")
    if not all(is_key(key) for key in keys):
        raise ValueError(f"{what}: invalid key in {describe(keys)}")
    return sorted(set(keys), key=lambda key: (isinstance(key, str), key))


def indexed(texts) -> dict:
    """{WORDS: the words of the texts}, for a node that can be searched, or {} if they hold
    no word. A list holds texts too. Anything that is not text has no words."""
    flat = [t for text in texts for t in (text if isinstance(text, list) else [text])]
    found = " ".join(w for text in flat if isinstance(text, str) for w in WORD.findall(text))
    return {WORDS: found} if found else {}


def without_words(found: dict) -> dict:
    """The properties of a node without its searchable text, which only the index reads."""
    return {name: value for name, value in found.items() if name != WORDS}
