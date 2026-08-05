"""Asynchronous PostgreSQL resource ownership and tenant transaction context."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from core.settings import Settings


class Database:
    """Own an async engine and issue explicit transactional sessions."""

    def __init__(
        self,
        settings: Settings,
        *,
        database_url: str | None = None,
    ) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url or settings.DATABASE_URL,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the owned engine for readiness and migration checks."""

        return self._engine

    @asynccontextmanager
    async def session(
        self,
        *,
        organization_id: UUID | None = None,
        identity_subject_id: UUID | None = None,
    ) -> AsyncIterator[AsyncSession]:
        """Yield one transaction with an optional trusted PostgreSQL tenant context."""

        async with self._session_factory() as session:
            try:
                async with session.begin():
                    if organization_id is not None:
                        await session.execute(
                            text(
                                "SELECT set_config("
                                "'app.organization_id', :organization_id, true)"
                            ),
                            {"organization_id": str(organization_id)},
                        )
                    if identity_subject_id is not None:
                        await session.execute(
                            text(
                                "SELECT set_config("
                                "'app.identity_subject_id', :identity_subject_id, true)"
                            ),
                            {"identity_subject_id": str(identity_subject_id)},
                        )
                    yield session
            except Exception:
                await session.rollback()
                raise

    async def ready(self) -> bool:
        """Return whether PostgreSQL can execute a trivial statement."""

        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def close(self) -> None:
        """Dispose the owned connection pool."""

        await self._engine.dispose()


class DatabaseResource(Protocol):
    """Describe lifecycle behavior used by the application composition root."""

    async def ready(self) -> bool:
        """Return whether the required data platform is available."""
        ...

    async def close(self) -> None:
        """Release resources owned by the implementation."""
        ...


__all__ = ["Database", "DatabaseResource"]
