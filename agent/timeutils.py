"""UTC-aware time helpers.

Every timestamp column in IRIS is `TIMESTAMPTZ`, so psycopg2 hands back aware
datetimes in UTC. The engines used to strip that offset and compare the result
against a naive `datetime.now()`, which is local time — so every analytical
window was wrong by the host's UTC offset. On this machine that was two hours
in summer and one in winter, meaning an occurrence near a window boundary could
change classification at a DST transition with no data having changed.

Everything time-related now goes through here: `utc_now()` for the current
moment, `to_utc()` for anything read back from the database or parsed from a
string.
"""

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """The current moment, timezone-aware, in UTC."""
    return datetime.now(UTC)


def to_utc(value) -> datetime | None:
    """Normalise a timestamp to an aware UTC datetime.

    Accepts aware and naive datetimes, dates, ISO-8601 strings and None. A
    naive value is taken to be UTC — which is what the database returns and
    what the engines were already assuming, just without saying so.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        # datetime must be checked before date: it is a subclass of it.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    raise TypeError(f"Cannot interpret {value!r} as a timestamp")
