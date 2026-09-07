"""PostgreSQL adapter for side-effect-free provider identity lookup."""

from sqlalchemy import select

from identity.domain.models import OwnIDSubject
from identity.infrastructure.models import OwnIDSubjectModel
from shared.database import Database


class SQLAlchemyIdentitySubjectReadRepository:
    """Read exact OwnID bindings without creating or updating subjects."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def find_by_provider_identity(
        self,
        *,
        issuer: str,
        subject: str,
    ) -> OwnIDSubject | None:
        """Return an existing subject only when issuer and subject both match."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(OwnIDSubjectModel).where(
                    OwnIDSubjectModel.issuer == issuer,
                    OwnIDSubjectModel.subject == subject,
                )
            )
        if model is None:
            return None
        return OwnIDSubject(
            id=model.id,
            issuer=model.issuer,
            subject=model.subject,
            email=model.email,
            display_name=model.display_name,
        )


__all__ = ["SQLAlchemyIdentitySubjectReadRepository"]
