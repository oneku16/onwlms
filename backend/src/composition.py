"""Explicit production composition root for the OwnSIS modular monolith."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from academic_adapters import AcademicGradeTargetAdapter
from academic_adapters import AcademicSchedulingResourceAdapter
from academic_adapters import AcademicTermClosureAdapter
from academic_adapters import AdmissionsAcademicTargetAdapter
from academics.composition import create_academic_services
from academics.composition import install_academic_routes
from admissions.composition import create_admissions_service
from admissions.composition import install_admissions_routes
from admissions_enrollment_adapter import (
    ModuleOwnedAcceptedApplicantEnrollmentRegistrar,
)
from audit.application.service import AuditService
from audit.infrastructure.repository import SQLAlchemyAuditRepository
from audit.infrastructure.sinks import ApplicationAuditSink
from audit.presentation.router import create_audit_router
from core.application import create_app
from core.field_encryption import FieldCipher
from core.settings import AppEnvironment
from core.settings import Settings
from course_selection_adapters import CourseSelectionStudentOwnershipAdapter
from entitlement_adapters import TimetableGenerationEntitlementAdapter
from entitlements.composition import create_entitlement_service
from entitlements.composition import install_entitlement_routes
from grading.composition import create_official_grading_service
from grading.composition import install_grading_routes
from identity.composition import create_identity_resources
from identity.composition import install_identity_routes
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf
from integrations.application.service import MoodleIntegrationService
from integrations.infrastructure.factory import MoodleGatewayFactoryAdapter
from integrations.infrastructure.grade_receiver import (
    ReviewRequiredGradeEvidenceReceiver,
)
from integrations.infrastructure.repository import SQLAlchemyMoodleIntegrationRepository
from integrations.presentation.router import create_integrations_router
from mcp_gateway.composition import MCPApplicationResources
from mcp_gateway.composition import create_mcp_application
from mcp_gateway.composition import create_self_service_read_resources
from mcp_gateway.composition import install_self_service_routes
from notifications.application.ports import NotificationChannelAdapter
from notifications.application.service import NotificationService
from notifications.domain.messages import NotificationChannel
from notifications.infrastructure.adapters import RecordingChannelAdapter
from notifications.infrastructure.adapters import UnavailableChannelAdapter
from notifications.infrastructure.repository import SQLAlchemyNotificationRepository
from notifications.presentation.router import create_notifications_router
from organizations.composition import create_organization_service
from organizations.composition import install_organization_routes
from people.application.accepted_student_service import (
    AcceptedStudentRegistrationService,
)
from people.application.read_service import PeopleOwnershipReadService
from people.composition import create_people_resources
from people.composition import install_people_routes
from people.infrastructure.read_repository import (
    SQLAlchemyPeopleOwnershipReadRepository,
)
from people_adapters import PeopleAcademicProfileAdapter
from people_adapters import PeopleSchedulingTeacherAdapter
from profile_activation_adapter import SQLAlchemyAcceptedStudentRegistrationWriter
from profile_activation_adapter import SQLAlchemyProfileActivationWriter
from provisioning.composition import create_provisioning_service
from provisioning.presentation.router import create_provisioning_router
from scheduling.composition import create_teacher_availability_service
from scheduling.composition import create_timetable_service
from scheduling.composition import install_scheduling_routes
from shared.database import Database


def create_application(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Compose production adapters, application services, routes, and lifecycle."""

    app_settings = settings or Settings()
    app_database = database or Database(app_settings)

    audit_service = AuditService(SQLAlchemyAuditRepository(app_database))
    audit_sink = ApplicationAuditSink(audit_service)
    identity = create_identity_resources(
        settings=app_settings,
        database=app_database,
        audit=audit_sink,
        platform_audit=audit_sink,
    )
    organization_service = create_organization_service(
        database=app_database,
        audit=audit_sink,
    )
    people = create_people_resources(
        database=app_database,
        pii_encryption_key=app_settings.PII_ENCRYPTION_KEY,
        organizations=organization_service,
        audit=audit_sink,
        profile_activations=SQLAlchemyProfileActivationWriter(
            database=app_database,
            pii_encryption_key=app_settings.PII_ENCRYPTION_KEY,
        ),
    )
    entitlement_service = create_entitlement_service(
        database=app_database,
        organizations=organization_service,
        audit=audit_sink,
    )
    people_ownership = PeopleOwnershipReadService(
        repository=SQLAlchemyPeopleOwnershipReadRepository(
            database=app_database,
            encryption_key=app_settings.PII_ENCRYPTION_KEY,
        ),
        memberships=people.memberships,
    )
    scheduling_teachers = PeopleSchedulingTeacherAdapter(people.references)
    teacher_availability = create_teacher_availability_service(
        database=app_database,
        teachers=scheduling_teachers,
        audit=audit_sink,
    )

    academic_services = create_academic_services(
        database=app_database,
        campuses=organization_service,
        profiles=PeopleAcademicProfileAdapter(people.references),
        audit=audit_sink,
        ownership=CourseSelectionStudentOwnershipAdapter(people_ownership),
    )
    grading_service = create_official_grading_service(
        database=app_database,
        targets=AcademicGradeTargetAdapter(academic_services.references),
        terms=AcademicTermClosureAdapter(academic_services.references),
        audit=audit_sink,
    )
    scheduling_resources = AcademicSchedulingResourceAdapter(
        academic_services.references,
        teacher_availability,
        scheduling_teachers,
    )
    timetable_service = create_timetable_service(
        database=app_database,
        resources=scheduling_resources,
        references=scheduling_resources,
        audit=audit_sink,
        entitlements=TimetableGenerationEntitlementAdapter(entitlement_service),
    )
    admissions_service = create_admissions_service(
        database=app_database,
        pii_encryption_key=app_settings.PII_ENCRYPTION_KEY,
        audit=audit_sink,
        targets=AdmissionsAcademicTargetAdapter(academic_services.references),
        registrar=ModuleOwnedAcceptedApplicantEnrollmentRegistrar(
            people=AcceptedStudentRegistrationService(
                writer=SQLAlchemyAcceptedStudentRegistrationWriter(
                    database=app_database,
                    pii_encryption_key=app_settings.PII_ENCRYPTION_KEY,
                )
            ),
            academics=academic_services.admissions_enrollment,
        ),
    )

    integration_cipher = FieldCipher(app_settings.INTEGRATION_ENCRYPTION_KEY)
    integration_repository = SQLAlchemyMoodleIntegrationRepository(app_database)
    moodle_gateway_factory = MoodleGatewayFactoryAdapter(
        repository=integration_repository,
        cipher=integration_cipher,
        timeout_seconds=app_settings.MOODLE_REQUEST_TIMEOUT_SECONDS,
    )
    moodle_service = MoodleIntegrationService(
        repository=integration_repository,
        gateway_factory=moodle_gateway_factory,
        grade_receiver=ReviewRequiredGradeEvidenceReceiver(),
        cipher=integration_cipher,
        audit=audit_sink,
    )
    self_service = create_self_service_read_resources(
        settings=app_settings,
        database=app_database,
        memberships=people.memberships,
        moodle_repository=integration_repository,
        moodle_gateway_factory=moodle_gateway_factory,
    )
    notification_service = NotificationService(
        repository=SQLAlchemyNotificationRepository(app_database),
        adapters=_notification_adapters(app_settings),
        recipients=people.memberships,
    )
    provisioning_service = create_provisioning_service(
        settings=app_settings,
        database=app_database,
        audit=audit_sink,
    )

    shutdown_callbacks = [app_database.close] if database is None else []
    if identity.owned_http_client is not None:
        shutdown_callbacks.append(identity.owned_http_client.aclose)
    app = create_app(
        settings=app_settings,
        database=app_database,
        shutdown_callbacks=shutdown_callbacks,
    )
    app.state.audit_service = audit_service
    app.state.moodle_service = moodle_service
    app.state.notification_service = notification_service
    app.state.provisioning_service = provisioning_service

    install_identity_routes(
        app=app,
        service=identity.service,
        platform_administration=identity.platform_administration,
    )
    install_organization_routes(app=app, service=organization_service)
    install_people_routes(app=app, resources=people)
    install_entitlement_routes(app=app, service=entitlement_service)
    install_academic_routes(app=app, services=academic_services)
    install_admissions_routes(app=app, service=admissions_service)
    install_grading_routes(app=app, service=grading_service)
    install_scheduling_routes(
        app=app,
        service=timetable_service,
        teacher_availability=teacher_availability,
    )
    install_self_service_routes(
        app=app,
        resources=self_service,
        actor_dependency=require_actor,
    )
    app.include_router(create_audit_router(require_actor))
    app.include_router(
        create_integrations_router(
            actor_dependency=require_actor,
            csrf_dependency=require_csrf,
        )
    )
    app.include_router(
        create_notifications_router(
            actor_dependency=require_actor,
            csrf_dependency=require_csrf,
        )
    )
    app.include_router(
        create_provisioning_router(
            actor_dependency=require_actor,
            csrf_dependency=require_csrf,
        )
    )
    if app_settings.MCP_ENABLED:
        mcp = create_mcp_application(
            settings=app_settings,
            database=app_database,
            memberships=people.memberships,
            entitlements=entitlement_service,
            audit=audit_sink,
            self_service=self_service,
        )
        _install_mcp_application(app=app, resources=mcp)
    return app


def _install_mcp_application(
    *,
    app: FastAPI,
    resources: MCPApplicationResources,
) -> None:
    """Mount MCP and compose its session-manager lifecycle with FastAPI."""

    root_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(root_app: FastAPI) -> AsyncIterator[None]:
        async with root_lifespan(root_app):
            async with resources.mounted_lifespan():
                yield

    app.router.lifespan_context = combined_lifespan
    app.state.mcp_server = resources.server
    app.mount("/mcp", resources.asgi_app, name="mcp")


def _notification_adapters(settings: Settings) -> list[NotificationChannelAdapter]:
    """Select explicit local recorders or fail-closed production adapters."""

    channels = [
        channel
        for channel in NotificationChannel
        if channel is not NotificationChannel.IN_APP
    ]
    if settings.APP_ENV is AppEnvironment.PRODUCTION:
        return [UnavailableChannelAdapter(channel) for channel in channels]
    return [RecordingChannelAdapter(channel) for channel in channels]


__all__ = ["create_application"]
