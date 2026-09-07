"""Persistent identifier primitives."""

from uuid import UUID
from uuid import uuid7


def new_uuid7() -> UUID:
    """Create a time-ordered UUIDv7 persistent identifier."""

    return uuid7()


__all__ = ["new_uuid7"]
