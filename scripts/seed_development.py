"""Create explicit, synthetic, idempotent local-development data."""

import asyncio

from sqlalchemy import select

from core.settings import AppEnvironment
from core.settings import Settings
from core.time import utc_now
from entitlements.domain.models import BASE_FEATURES
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import SubscriptionStatus
from entitlements.infrastructure.models import FeatureModel
from entitlements.infrastructure.models import PlanFeatureModel
from entitlements.infrastructure.models import PlanModel
from entitlements.infrastructure.models import SubscriptionModel
from identity.infrastructure.models import OwnIDSubjectModel
from identity.infrastructure.models import PlatformAdministratorModel
from organizations.domain.models import EducationMode
from organizations.domain.models import OrganizationStatus
from organizations.domain.models import OrganizationType
from organizations.infrastructure.models import CampusModel
from organizations.infrastructure.models import OrganizationModel
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus
from people.infrastructure.models import MembershipModel
from people.infrastructure.models import MembershipRoleModel
from people.infrastructure.models import PersonModel
from shared.database import Database


async def seed() -> None:
    """Seed a local-only platform admin, tenant owner, and base plan."""

    settings = Settings()
    if settings.APP_ENV is not AppEnvironment.LOCAL:
        message = "Development seed is available only in the local environment"
        raise RuntimeError(message)
    database = Database(settings)
    try:
        async with database.session() as session:
            subject = await session.scalar(
                select(OwnIDSubjectModel).where(
                    OwnIDSubjectModel.issuer == "urn:ownsis:development",
                    OwnIDSubjectModel.subject == settings.DEV_AUTH_SUBJECT,
                )
            )
            if subject is None:
                subject = OwnIDSubjectModel(
                    issuer="urn:ownsis:development",
                    subject=settings.DEV_AUTH_SUBJECT,
                    display_name="Development Platform Administrator",
                )
                session.add(subject)
                await session.flush()
            platform_admin = await session.scalar(
                select(PlatformAdministratorModel).where(
                    PlatformAdministratorModel.subject_id == subject.id
                )
            )
            if platform_admin is None:
                session.add(
                    PlatformAdministratorModel(
                        subject_id=subject.id,
                        active=True,
                    )
                )
            organization = await session.scalar(
                select(OrganizationModel).where(OrganizationModel.slug == "ownsis-demo")
            )
            if organization is None:
                organization = OrganizationModel(
                    slug="ownsis-demo",
                    organization_type=OrganizationType.UNIVERSITY.value,
                    status=OrganizationStatus.ACTIVE.value,
                    display_name="OwnSIS Demo University",
                    primary_color="#1D4ED8",
                    secondary_color="#0F172A",
                    locale="en",
                    timezone="Asia/Bishkek",
                    education_mode=EducationMode.HYBRID.value,
                )
                session.add(organization)
                await session.flush()
            for code in FeatureCode:
                feature = await session.scalar(
                    select(FeatureModel).where(FeatureModel.code == code.value)
                )
                if feature is None:
                    feature = FeatureModel(
                        code=code.value,
                        display_name=code.value.replace("_", " ").title(),
                        base_included=code in BASE_FEATURES,
                    )
                    session.add(feature)
            plan = await session.scalar(
                select(PlanModel).where(PlanModel.code == "development-base")
            )
            if plan is None:
                plan = PlanModel(
                    code="development-base",
                    display_name="Development Base",
                    active=True,
                )
                session.add(plan)
                await session.flush()
            for code in BASE_FEATURES:
                grant = await session.get(PlanFeatureModel, (plan.id, code.value))
                if grant is None:
                    session.add(
                        PlanFeatureModel(
                            plan_id=plan.id,
                            feature_code=code.value,
                        )
                    )
            subject_id = subject.id
            organization_id = organization.id
            plan_id = plan.id

        async with database.session(organization_id=organization_id) as session:
            person = await session.scalar(
                select(PersonModel).where(
                    PersonModel.organization_id == organization_id,
                    PersonModel.given_name == "Development",
                    PersonModel.family_name == "Administrator",
                )
            )
            if person is None:
                person = PersonModel(
                    organization_id=organization_id,
                    given_name="Development",
                    family_name="Administrator",
                )
                session.add(person)
                await session.flush()
            membership = await session.scalar(
                select(MembershipModel).where(
                    MembershipModel.organization_id == organization_id,
                    MembershipModel.identity_subject_id == subject_id,
                )
            )
            if membership is None:
                membership = MembershipModel(
                    organization_id=organization_id,
                    identity_subject_id=subject_id,
                    person_id=person.id,
                    status=MembershipStatus.ACTIVE.value,
                )
                session.add(membership)
                await session.flush()
            role = await session.get(
                MembershipRoleModel,
                (membership.id, MembershipRole.ORGANIZATION_OWNER.value),
            )
            if role is None:
                session.add(
                    MembershipRoleModel(
                        membership_id=membership.id,
                        organization_id=organization_id,
                        role=MembershipRole.ORGANIZATION_OWNER.value,
                    )
                )
            campus = await session.scalar(
                select(CampusModel).where(
                    CampusModel.organization_id == organization_id,
                    CampusModel.code == "MAIN",
                )
            )
            if campus is None:
                session.add(
                    CampusModel(
                        organization_id=organization_id,
                        code="MAIN",
                        name="Main Campus",
                        active=True,
                    )
                )
            subscription = await session.scalar(
                select(SubscriptionModel).where(
                    SubscriptionModel.organization_id == organization_id
                )
            )
            if subscription is None:
                session.add(
                    SubscriptionModel(
                        organization_id=organization_id,
                        plan_id=plan_id,
                        status=SubscriptionStatus.ACTIVE.value,
                        starts_at=utc_now(),
                    )
                )
        print("Seeded synthetic development tenant and administrator.")
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed())
