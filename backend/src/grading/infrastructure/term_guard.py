"""PostgreSQL serialization guard between grade writes and term closure."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from core.errors import ConflictError
from shared.database import Database


def _term_grade_lock_key(*, organization_id: UUID, term_id: UUID) -> int:
    """Derive the stable signed lock key shared with Academic term closure."""

    digest = hashlib.blake2b(digest_size=8, person=b"ownsis-termgrade")
    digest.update(organization_id.bytes)
    digest.update(term_id.bytes)
    return int.from_bytes(digest.digest(), byteorder="big", signed=True)


class SQLAlchemyTermGradeWriteGuard:
    """Hold shared transaction protection across closure check and grade commit."""

    def __init__(self, database: Database) -> None:
        self._guard_engine: AsyncEngine = create_async_engine(
            database.engine.url,
            hide_parameters=True,
            poolclass=NullPool,
        )

    @asynccontextmanager
    async def hold_grade_write(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> AsyncIterator[None]:
        """Fail fast unless the tenant term is available for a grade write."""

        # A dedicated non-pooled connection keeps the application pool available
        # to the Academic recheck, audit sink, and Grading repository while this
        # transaction owns the cross-module guard.
        async with self._guard_engine.begin() as connection:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_xact_lock_shared(:lock_key)"),
                {
                    "lock_key": _term_grade_lock_key(
                        organization_id=organization_id,
                        term_id=term_id,
                    )
                },
            )
            if acquired is not True:
                raise ConflictError(
                    "Term grading state is being updated; retry the request."
                )
            yield


__all__ = ["SQLAlchemyTermGradeWriteGuard"]
