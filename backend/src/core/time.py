"""Central timezone-aware clock helpers."""

from datetime import UTC
from datetime import datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


__all__ = ["utc_now"]
