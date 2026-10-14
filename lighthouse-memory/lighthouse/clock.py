"""Times in the one form the library sends to FalkorDB."""

from datetime import UTC, datetime, timedelta

# A source clock may run this far ahead of ours. A time later than that is refused.
MAX_AHEAD = timedelta(minutes=5)


def stamp(value: str | datetime | None) -> str | None:
    """A time as `YYYY-MM-DDTHH:MM:SS` in UTC, the form FalkorDB's localdatetime() parses.

    FalkorDB keeps whole seconds, so fractions are dropped. A time without an offset is
    taken as UTC. The client cannot send datetime parameters, so queries get this string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        if len(value) > 64:  # no time is this long; do not parse or quote it
            raise ValueError("not a time: the text is too long")
        value = datetime.fromisoformat(value.strip())
    if not isinstance(value, datetime):
        # The value is not quoted: it may be too deep or too large to print.
        raise TypeError(f"not a time: {type(value).__name__}")
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def now() -> str:
    return stamp(datetime.now(UTC))


def is_ahead(time: str) -> bool:
    """True for a time in the future. A fact that starts in the future would refuse every
    true fact that comes before it, so nothing may be dated ahead of the clock."""
    return time > stamp(datetime.now(UTC) + MAX_AHEAD)
