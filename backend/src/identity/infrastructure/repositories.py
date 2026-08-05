"""PostgreSQL identity, pending-flow, and server-session adapters."""

from typing import cast
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.exceptions import InvalidSessionError
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession
from identity.infrastructure.models import IdentitySessionModel
from identity.infrastructure.models import OwnIDSubjectModel
from identity.infrastructure.models import PendingOIDCFlowModel
from identity.infrastructure.models import PlatformAdministratorModel
from shared.database import Database


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
        """Lock and delete a pending request before returning its secret values."""

        async with self._database.session() as session:
            model = await session.scalar(
                select(PendingOIDCFlowModel)
                .where(PendingOIDCFlowModel.key_digest == key_digest)
                .with_for_update()
            )
            if model is None:
                return None
            pending = self._pending_to_domain(model)
            await session.delete(model)
            return pending

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

    async def replace_tokens(
        self,
        *,
        key_digest: str,
        expected_version: int,
        tokens: ProviderTokens,
    ) -> bool:
        """Replace encrypted tokens only when a session version matches."""

        async with self._database.session() as session:
            updated_version = cast(
                int | None,
                await session.scalar(
                    update(IdentitySessionModel)
                    .where(
                        IdentitySessionModel.key_digest == key_digest,
                        IdentitySessionModel.version == expected_version,
                    )
                    .values(
                        encrypted_access_token=self._encrypt(tokens.access_token),
                        encrypted_id_token=self._encrypt(tokens.id_token),
                        encrypted_refresh_token=(
                            self._encrypt(tokens.refresh_token)
                            if tokens.refresh_token is not None
                            else None
                        ),
                        provider_expires_at=tokens.expires_at,
                        version=expected_version + 1,
                    )
                    .returning(IdentitySessionModel.version)
                ),
            )
            return updated_version == expected_version + 1

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


__all__ = [
    "SQLAlchemySessionRepository",
    "SQLAlchemySubjectRepository",
]
