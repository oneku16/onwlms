"""PostgreSQL identity, pending-flow, and server-session adapters."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.exceptions import FinalPlatformAdministratorError
from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.exceptions import InvalidSessionError
from identity.domain.exceptions import PlatformAdministratorBootstrapClosedError
from identity.domain.exceptions import PlatformAdministratorNotFoundError
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import PlatformAdministrator
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession
from identity.infrastructure.models import IdentitySessionModel
from identity.infrastructure.models import OwnIDSubjectModel
from identity.infrastructure.models import PendingOIDCFlowModel
from identity.infrastructure.models import PlatformAdministratorModel
from shared.database import Database

_PLATFORM_ADMINISTRATOR_LOCK_ID = 1_331_123_795


class SQLAlchemySubjectRepository:
    """Resolve global OwnID subjects and separate platform privilege."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def resolve(
        self,
        *,
        issuer: str,
        subject: str,
        email: str | None,
        display_name: str | None,
    ) -> OwnIDSubject:
        """Resolve or atomically create one global issuer-subject binding."""

        try:
            async with self._database.session() as session:
                model = await session.scalar(
                    select(OwnIDSubjectModel).where(
                        OwnIDSubjectModel.issuer == issuer,
                        OwnIDSubjectModel.subject == subject,
                    )
                )
                if model is None:
                    model = OwnIDSubjectModel(
                        issuer=issuer,
                        subject=subject,
                        email=email,
                        display_name=display_name,
                    )
                    session.add(model)
                else:
                    model.email = email
                    model.display_name = display_name
            return self._to_domain(model)
        except IntegrityError:
            async with self._database.session() as session:
                existing = await session.scalar(
                    select(OwnIDSubjectModel).where(
                        OwnIDSubjectModel.issuer == issuer,
                        OwnIDSubjectModel.subject == subject,
                    )
                )
                if existing is None:
                    raise
                existing.email = email
                existing.display_name = display_name
                return self._to_domain(existing)

    async def get(
        self,
        *,
        subject_id: UUID,
    ) -> OwnIDSubject | None:
        """Return one global subject by its OwnSIS identifier."""

        async with self._database.session() as session:
            model = await session.get(OwnIDSubjectModel, subject_id)
            return self._to_domain(model) if model is not None else None

    async def is_platform_admin(
        self,
        *,
        subject_id: UUID,
    ) -> bool:
        """Return active platform privilege kept outside tenant roles."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(PlatformAdministratorModel).where(
                    PlatformAdministratorModel.subject_id == subject_id,
                    PlatformAdministratorModel.active.is_(True),
                )
            )
            return model is not None

    @staticmethod
    def _to_domain(model: OwnIDSubjectModel) -> OwnIDSubject:
        """Translate a persistence row into the global identity value."""

        return OwnIDSubject(
            id=model.id,
            issuer=model.issuer,
            subject=model.subject,
            email=model.email,
            display_name=model.display_name,
        )


class _SQLAlchemySessionRefreshClaim:
    """Update one session through the transaction that row-locked it."""

    def __init__(
        self,
        *,
        database_session: AsyncSession,
        model: IdentitySessionModel,
        stored: StoredSession,
        fernet: Fernet,
    ) -> None:
        self._database_session = database_session
        self._model = model
        self._stored = stored
        self._fernet = fernet

    @property
    def stored(self) -> StoredSession:
        """Return the decrypted state protected by the row lock."""

        return self._stored

    async def replace_tokens(self, tokens: ProviderTokens) -> None:
        """Store one successful rotation without opening another transaction."""

        self._model.encrypted_access_token = self._encrypt(tokens.access_token)
        self._model.encrypted_id_token = self._encrypt(tokens.id_token)
        self._model.encrypted_refresh_token = (
            self._encrypt(tokens.refresh_token)
            if tokens.refresh_token is not None
            else None
        )
        self._model.provider_expires_at = tokens.expires_at
        self._model.version = self._stored.version + 1

    async def delete(self) -> None:
        """Delete the locked session after a failed provider exchange."""

        await self._database_session.delete(self._model)

    def _encrypt(self, value: str) -> str:
        """Encrypt provider material with the repository-owned key."""

        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")


class SQLAlchemySessionRepository:
    """Store hashed opaque identifiers and Fernet-encrypted secret strings."""

    def __init__(
        self,
        *,
        database: Database,
        encryption_key: str,
    ) -> None:
        self._database = database
        self._fernet = Fernet(encryption_key.encode("ascii"))

    async def save_pending(
        self,
        pending: PendingAuthorization,
    ) -> None:
        """Persist a pending OIDC request with encrypted PKCE and nonce values."""

        async with self._database.session() as session:
            session.add(
                PendingOIDCFlowModel(
                    key_digest=pending.key_digest,
                    state_digest=pending.state_digest,
                    encrypted_nonce=self._encrypt(pending.nonce),
                    encrypted_code_verifier=self._encrypt(pending.code_verifier),
                    return_path=pending.return_path,
                    expires_at=pending.expires_at,
                )
            )

    async def consume_pending(
        self,
        *,
        key_digest: str,
    ) -> PendingAuthorization | None:
        """Atomically consume a pending request and return its secret values."""

        async with self._database.session() as session:
            model = await session.scalar(
                delete(PendingOIDCFlowModel)
                .where(PendingOIDCFlowModel.key_digest == key_digest)
                .returning(PendingOIDCFlowModel)
            )
            if model is None:
                return None
            return self._pending_to_domain(model)

    async def save_session(
        self,
        session_record: StoredSession,
    ) -> None:
        """Persist one server session without storing raw browser secrets."""

        async with self._database.session() as session:
            session.add(self._session_to_model(session_record))

    async def get_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        """Return one server session by its browser-token digest."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(IdentitySessionModel).where(
                    IdentitySessionModel.key_digest == key_digest,
                )
            )
            return self._session_to_domain(model) if model is not None else None

    @asynccontextmanager
    async def lock_for_refresh(
        self,
        *,
        key_digest: str,
    ) -> AsyncIterator[_SQLAlchemySessionRefreshClaim | None]:
        """Hold a row lock across exactly one provider token exchange."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(IdentitySessionModel)
                .where(IdentitySessionModel.key_digest == key_digest)
                .with_for_update()
            )
            if model is None:
                yield None
                return
            yield _SQLAlchemySessionRefreshClaim(
                database_session=session,
                model=model,
                stored=self._session_to_domain(model),
                fernet=self._fernet,
            )

    async def delete_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        """Lock and delete one local session before returning its token material."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(IdentitySessionModel)
                .where(IdentitySessionModel.key_digest == key_digest)
                .with_for_update()
            )
            if model is None:
                return None
            stored = self._session_to_domain(model)
            await session.delete(model)
            return stored

    async def delete_session_if_version(
        self,
        *,
        key_digest: str,
        expected_version: int,
    ) -> StoredSession | None:
        """Delete only when no concurrent refresh has replaced the tokens."""

        async with self._database.session() as session:
            model = await session.scalar(
                delete(IdentitySessionModel)
                .where(
                    IdentitySessionModel.key_digest == key_digest,
                    IdentitySessionModel.version == expected_version,
                )
                .returning(IdentitySessionModel)
            )
            return self._session_to_domain(model) if model is not None else None

    def _session_to_model(
        self,
        stored: StoredSession,
    ) -> IdentitySessionModel:
        """Encrypt provider token strings for persistence."""

        return IdentitySessionModel(
            key_digest=stored.key_digest,
            subject_id=stored.subject_id,
            csrf_digest=stored.csrf_digest,
            encrypted_access_token=self._encrypt(stored.tokens.access_token),
            encrypted_id_token=self._encrypt(stored.tokens.id_token),
            encrypted_refresh_token=(
                self._encrypt(stored.tokens.refresh_token)
                if stored.tokens.refresh_token is not None
                else None
            ),
            provider_expires_at=stored.tokens.expires_at,
            expires_at=stored.expires_at,
            version=stored.version,
        )

    def _session_to_domain(
        self,
        model: IdentitySessionModel,
    ) -> StoredSession:
        """Decrypt a session only inside the infrastructure adapter."""

        try:
            access_token = self._decrypt(model.encrypted_access_token)
            id_token = self._decrypt(model.encrypted_id_token)
            refresh_token = (
                self._decrypt(model.encrypted_refresh_token)
                if model.encrypted_refresh_token is not None
                else None
            )
        except InvalidToken as exc:
            raise InvalidSessionError from exc
        return StoredSession(
            key_digest=model.key_digest,
            subject_id=model.subject_id,
            csrf_digest=model.csrf_digest,
            tokens=ProviderTokens(
                access_token=access_token,
                id_token=id_token,
                refresh_token=refresh_token,
                expires_at=model.provider_expires_at,
            ),
            expires_at=model.expires_at,
            version=model.version,
        )

    def _pending_to_domain(
        self,
        model: PendingOIDCFlowModel,
    ) -> PendingAuthorization:
        """Decrypt pending flow secrets only during single-use consumption."""

        try:
            nonce = self._decrypt(model.encrypted_nonce)
            code_verifier = self._decrypt(model.encrypted_code_verifier)
        except InvalidToken as exc:
            raise InvalidAuthorizationFlowError from exc
        return PendingAuthorization(
            key_digest=model.key_digest,
            state_digest=model.state_digest,
            nonce=nonce,
            code_verifier=code_verifier,
            return_path=model.return_path,
            expires_at=model.expires_at,
        )

    def _encrypt(
        self,
        value: str,
    ) -> str:
        """Encrypt one secret string with the configured session key."""

        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(
        self,
        value: str,
    ) -> str:
        """Decrypt one secret string and propagate invalid-token failure."""

        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")


class SQLAlchemyPlatformAdministratorRepository:
    """Serialize global administrator changes and preserve a final administrator."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def bootstrap(
        self,
        *,
        subject_id: UUID,
    ) -> PlatformAdministrator:
        """Assign the first administrator under a transaction-scoped lock."""

        async with self._database.session() as session:
            await self._lock_governance(session)
            await self._require_subject(session=session, subject_id=subject_id)
            active_count = await self._active_count(session)
            if active_count:
                raise PlatformAdministratorBootstrapClosedError(
                    "Platform administrator bootstrap is already closed"
                )
            model = await session.scalar(
                select(PlatformAdministratorModel).where(
                    PlatformAdministratorModel.subject_id == subject_id,
                )
            )
            if model is None:
                model = PlatformAdministratorModel(
                    subject_id=subject_id,
                    active=True,
                )
                session.add(model)
            else:
                model.active = True
            return self._to_domain(model)

    async def assign(
        self,
        *,
        subject_id: UUID,
    ) -> PlatformAdministrator:
        """Create or reactivate an assignment under serialized governance."""

        async with self._database.session() as session:
            await self._lock_governance(session)
            await self._require_subject(session=session, subject_id=subject_id)
            model = await session.scalar(
                select(PlatformAdministratorModel).where(
                    PlatformAdministratorModel.subject_id == subject_id,
                )
            )
            if model is None:
                model = PlatformAdministratorModel(
                    subject_id=subject_id,
                    active=True,
                )
                session.add(model)
            else:
                model.active = True
            return self._to_domain(model)

    async def revoke(
        self,
        *,
        subject_id: UUID,
    ) -> PlatformAdministrator:
        """Deactivate an assignment only when another active admin remains."""

        async with self._database.session() as session:
            await self._lock_governance(session)
            model = await session.scalar(
                select(PlatformAdministratorModel).where(
                    PlatformAdministratorModel.subject_id == subject_id,
                )
            )
            if model is None:
                raise PlatformAdministratorNotFoundError
            if not model.active:
                return self._to_domain(model)
            if await self._active_count(session) <= 1:
                raise FinalPlatformAdministratorError(
                    "The final active platform administrator cannot be revoked"
                )
            model.active = False
            return self._to_domain(model)

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[PlatformAdministrator]:
        """List bounded assignments without exposing provider identity claims."""

        async with self._database.session() as session:
            models = await session.scalars(
                select(PlatformAdministratorModel)
                .order_by(
                    PlatformAdministratorModel.created_at,
                    PlatformAdministratorModel.subject_id,
                )
                .limit(limit)
                .offset(offset)
            )
            return [self._to_domain(model) for model in models]

    @staticmethod
    async def _lock_governance(session: AsyncSession) -> None:
        """Serialize empty-set bootstrap and final-admin checks in PostgreSQL."""

        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _PLATFORM_ADMINISTRATOR_LOCK_ID},
        )

    @staticmethod
    async def _require_subject(
        *,
        session: AsyncSession,
        subject_id: UUID,
    ) -> None:
        """Require a subject already established through OwnID sign-in."""

        subject = await session.get(OwnIDSubjectModel, subject_id)
        if subject is None:
            raise PlatformAdministratorNotFoundError

    @staticmethod
    async def _active_count(session: AsyncSession) -> int:
        """Count active administrators while the governance lock is held."""

        count = await session.scalar(
            select(func.count())
            .select_from(PlatformAdministratorModel)
            .where(PlatformAdministratorModel.active.is_(True))
        )
        return int(count or 0)

    @staticmethod
    def _to_domain(model: PlatformAdministratorModel) -> PlatformAdministrator:
        """Translate one assignment row into its safe domain value."""

        return PlatformAdministrator(
            subject_id=model.subject_id,
            active=model.active,
        )


__all__ = [
    "SQLAlchemyPlatformAdministratorRepository",
    "SQLAlchemySessionRepository",
    "SQLAlchemySubjectRepository",
]
