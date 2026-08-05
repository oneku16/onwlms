"""PostgreSQL organization and campus repository adapters."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import ConflictError
from organizations.domain.exceptions import OrganizationNotFoundError
from organizations.domain.exceptions import OrganizationSlugConflictError
from organizations.domain.models import Campus
from organizations.domain.models import CustomDomainMetadata
from organizations.domain.models import DomainVerificationStatus
from organizations.domain.models import EducationMode
from organizations.domain.models import LogoMetadata
from organizations.domain.models import Organization
from organizations.domain.models import OrganizationBranding
from organizations.domain.models import OrganizationConfiguration
from organizations.domain.models import OrganizationStatus
from organizations.domain.models import OrganizationType
from organizations.infrastructure.models import CampusModel
from organizations.infrastructure.models import OrganizationModel
from shared.database import Database


class SQLAlchemyOrganizationRepository:
    """Persist organization state through explicit platform and tenant paths."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def add(
        self,
        organization: Organization,
    ) -> None:
        """Create an organization and translate global uniqueness conflicts."""

        try:
            async with self._database.session() as session:
                session.add(self._to_model(organization))
        except IntegrityError as exc:
            raise OrganizationSlugConflictError(
                "Organization slug or custom domain already exists"
            ) from exc

    async def get_platform(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        """Return one organization's governance metadata for a platform operation."""

        async with self._database.session() as session:
            model = await session.get(OrganizationModel, organization_id)
            return self._to_domain(model) if model is not None else None

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Organization]:
        """List bounded organization governance metadata for platform views."""

        async with self._database.session() as session:
            models = await session.scalars(
                select(OrganizationModel)
                .order_by(OrganizationModel.slug)
                .limit(limit)
                .offset(offset)
            )
            return [self._to_domain(model) for model in models]

    async def get_tenant(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        """Return one organization under a matching PostgreSQL tenant context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(OrganizationModel).where(
                    OrganizationModel.id == organization_id,
                )
            )
            return self._to_domain(model) if model is not None else None

    async def save_platform(
        self,
        organization: Organization,
    ) -> None:
        """Persist lifecycle state through the privileged platform path."""

        async with self._database.session() as session:
            await self._save(session=session, organization=organization)

    async def save_tenant(
        self,
        organization: Organization,
    ) -> None:
        """Persist tenant configuration under its PostgreSQL tenant context."""

        try:
            async with self._database.session(
                organization_id=organization.id,
            ) as session:
                await self._save(session=session, organization=organization)
        except IntegrityError as exc:
            raise ConflictError("Custom domain already exists") from exc

    async def _save(
        self,
        *,
        session: AsyncSession,
        organization: Organization,
    ) -> None:
        """Lock and update one organization without accepting detached state."""

        model = await session.scalar(
            select(OrganizationModel)
            .where(OrganizationModel.id == organization.id)
            .with_for_update()
        )
        if model is None:
            raise OrganizationNotFoundError
        self._apply(model=model, organization=organization)

    @staticmethod
    def _to_model(organization: Organization) -> OrganizationModel:
        """Translate one domain aggregate into an owned persistence row."""

        model = OrganizationModel(id=organization.id)
        SQLAlchemyOrganizationRepository._apply(
            model=model,
            organization=organization,
        )
        return model

    @staticmethod
    def _apply(
        *,
        model: OrganizationModel,
        organization: Organization,
    ) -> None:
        """Apply complete validated organization state to a persistence row."""

        branding = organization.branding
        configuration = organization.configuration
        logo = branding.logo
        custom_domain = configuration.custom_domain
        model.slug = organization.slug
        model.organization_type = organization.organization_type.value
        model.status = organization.status.value
        model.display_name = branding.display_name
        model.primary_color = branding.primary_color
        model.secondary_color = branding.secondary_color
        model.logo_file_name = logo.file_name if logo is not None else None
        model.logo_content_type = logo.content_type if logo is not None else None
        model.logo_size_bytes = logo.size_bytes if logo is not None else None
        model.logo_object_key = logo.object_key if logo is not None else None
        model.locale = configuration.locale
        model.timezone = configuration.timezone
        model.education_mode = configuration.education_mode.value
        model.custom_domain = (
            custom_domain.domain if custom_domain is not None else None
        )
        model.custom_domain_status = (
            custom_domain.verification_status.value
            if custom_domain is not None
            else None
        )
        model.ownid_tenant_reference = configuration.ownid_tenant_reference
        model.ownid_client_reference = configuration.ownid_client_reference

    @staticmethod
    def _to_domain(model: OrganizationModel) -> Organization:
        """Translate persistence state into a validated organization aggregate."""

        logo = None
        if (
            model.logo_file_name is not None
            and model.logo_content_type is not None
            and model.logo_size_bytes is not None
            and model.logo_object_key is not None
        ):
            logo = LogoMetadata(
                file_name=model.logo_file_name,
                content_type=model.logo_content_type,
                size_bytes=model.logo_size_bytes,
                object_key=model.logo_object_key,
            )
        custom_domain = None
        if model.custom_domain is not None and model.custom_domain_status is not None:
            custom_domain = CustomDomainMetadata(
                domain=model.custom_domain,
                verification_status=DomainVerificationStatus(
                    model.custom_domain_status
                ),
            )
        return Organization(
            id=model.id,
            slug=model.slug,
            organization_type=OrganizationType(model.organization_type),
            status=OrganizationStatus(model.status),
            branding=OrganizationBranding(
                display_name=model.display_name,
                primary_color=model.primary_color,
                secondary_color=model.secondary_color,
                logo=logo,
            ),
            configuration=OrganizationConfiguration(
                locale=model.locale,
                timezone=model.timezone,
                education_mode=EducationMode(model.education_mode),
                custom_domain=custom_domain,
                ownid_tenant_reference=model.ownid_tenant_reference,
                ownid_client_reference=model.ownid_client_reference,
            ),
        )


class SQLAlchemyCampusRepository:
    """Persist campuses with organization predicates and database tenant context."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def add(
        self,
        campus: Campus,
    ) -> None:
        """Create one campus and translate tenant-local code conflicts."""

        try:
            async with self._database.session(
                organization_id=campus.organization_id,
            ) as session:
                session.add(
                    CampusModel(
                        id=campus.id,
                        organization_id=campus.organization_id,
                        code=campus.code,
                        name=campus.name,
                        active=campus.active,
                    )
                )
        except IntegrityError as exc:
            raise ConflictError("Campus code already exists") from exc

    async def get(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> Campus | None:
        """Return one campus only when its identifier and tenant both match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(CampusModel).where(
                    CampusModel.id == campus_id,
                    CampusModel.organization_id == organization_id,
                )
            )
            return self._to_domain(model) if model is not None else None

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
    ) -> list[Campus]:
        """List campuses using both SQL predicate and PostgreSQL tenant context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = await session.scalars(
                select(CampusModel)
                .where(CampusModel.organization_id == organization_id)
                .order_by(CampusModel.code)
            )
            return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: CampusModel) -> Campus:
        """Translate a persistence row into one campus domain value."""

        return Campus(
            id=model.id,
            organization_id=model.organization_id,
            code=model.code,
            name=model.name,
            active=model.active,
        )


__all__ = [
    "SQLAlchemyCampusRepository",
    "SQLAlchemyOrganizationRepository",
]
